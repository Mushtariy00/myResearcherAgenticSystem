"""Run cost estimates for the new-run wizard: a heuristic that returns every assumption it used.

Each pipeline step makes a typical number of calls (low, expected and high counts) of a typical
size, and a call costs its tokens at the paid chain's prices. The low end prices every call with
the chain's cheapest model, the expected value with its first (the one the gateway tries first)
and the high end with its most expensive, because fallbacks happen. Free models cost nothing,
so a run that cannot use paid models is estimated at zero.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Literal

from agentic_api.demo.catalog import CATALOG
from agentic_api.schemas import (
    AgentRole,
    EstimateAssumptions,
    EstimateStepOut,
    ModelPriceOut,
    RunEstimateOut,
)
from agentic_core.enums import LlmPolicy
from agentic_core.schemas import RunConfig
from agentic_core.stages import Stage

# Assumed for a paid model the catalog does not list; on the expensive side on purpose.
UNKNOWN_PROMPT_USD_PER_MTOK = Decimal("3.00")
UNKNOWN_COMPLETION_USD_PER_MTOK = Decimal("15.00")
_PRECISION = Decimal("0.0001")
_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class Step:
    stage: Stage
    role: AgentRole
    prompt_tokens: int  # per call
    completion_tokens: int
    calls: tuple[int, int, int]  # low, expected, high
    per_100_papers: tuple[int, int, int] = (0, 0, 0)  # more calls per 100 of max_papers

    def counts(self, config: RunConfig) -> tuple[int, int, int]:
        low, expected, high = (
            base - (-rate * config.max_papers // 100)  # base + ceil(rate * papers / 100)
            for base, rate in zip(self.calls, self.per_100_papers, strict=True)
        )
        return low, expected, high


STEPS: tuple[Step, ...] = (
    # Plan the search and write the synthesis; each may need one repair.
    Step(Stage.LITERATURE, "researcher", 1_800, 900, (2, 2, 4)),
    # Search returns about twice max_papers candidates, screened ten per call.
    Step(Stage.LITERATURE, "screener", 4_500, 700, (0, 0, 0), (10, 20, 30)),
    # One reading-notes call per included paper (30% to all of them; 45% typically).
    Step(Stage.LITERATURE, "analyst", 7_000, 900, (0, 0, 0), (30, 45, 100)),
    Step(Stage.METHOD, "methodologist", 9_000, 1_800, (1, 2, 4)),
    # Write the model and loss, then up to three smoke-test repairs.
    Step(Stage.CODING, "coder", 7_000, 3_500, (1, 3, 6)),
    # The harness owns training; one call summarizes the results.
    Step(Stage.EXPERIMENT, "analyst", 3_500, 700, (1, 1, 2)),
    Step(Stage.WRITING, "writer", 12_000, 4_000, (2, 3, 5)),
)


def chain_prices(chain: Sequence[str]) -> list[ModelPriceOut]:
    prices = []
    for model_id in chain:
        model = CATALOG.get(model_id)
        prices.append(
            ModelPriceOut(
                id=model_id,
                prompt_usd_per_mtok=model.prompt_usd_per_mtok
                if model
                else UNKNOWN_PROMPT_USD_PER_MTOK,
                completion_usd_per_mtok=model.completion_usd_per_mtok
                if model
                else UNKNOWN_COMPLETION_USD_PER_MTOK,
                known=model is not None,
            )
        )
    return prices


def _call_usd(step: Step, price: ModelPriceOut) -> Decimal:
    return (
        step.prompt_tokens * price.prompt_usd_per_mtok
        + step.completion_tokens * price.completion_usd_per_mtok
    ) / _MILLION


def _money(value: Decimal, rounding: str) -> Decimal:
    return value.quantize(_PRECISION, rounding=rounding)


def estimate_run(
    config: RunConfig,
    policy: LlmPolicy,
    *,
    paid_chain: Sequence[str],
    paid_models_enabled: bool,
    budget_remaining_usd: Decimal,
    budget_cap_usd: Decimal | None = None,
) -> RunEstimateOut:
    """The estimate for a run with ``config``, charged to someone with ``budget_remaining_usd``
    of paid budget left this month."""
    prices = chain_prices(paid_chain)
    steps: list[EstimateStepOut] = []
    for step in STEPS:
        if step.stage not in config.stages:
            continue
        low_calls, expected_calls, high_calls = step.counts(config)
        per_call = [_call_usd(step, price) for price in prices]
        steps.append(
            EstimateStepOut(
                stage=step.stage.value,
                role=step.role,
                calls_low=low_calls,
                calls_expected=expected_calls,
                calls_high=high_calls,
                prompt_tokens_per_call=step.prompt_tokens,
                completion_tokens_per_call=step.completion_tokens,
                low_usd=_money(low_calls * min(per_call), ROUND_FLOOR),
                expected_usd=_money(expected_calls * per_call[0], ROUND_HALF_UP),
                high_usd=_money(high_calls * max(per_call), ROUND_CEILING),
            )
        )

    blocked_by: Literal["policy", "kill_switch", "budget", "run_cap"] | None = None
    if policy == LlmPolicy.FREE:
        blocked_by = "policy"
    elif not paid_models_enabled:
        blocked_by = "kill_switch"
    elif budget_remaining_usd <= 0:
        blocked_by = "budget"
    elif budget_cap_usd is not None and budget_cap_usd <= 0:
        blocked_by = "run_cap"

    low = sum((step.low_usd for step in steps), Decimal(0))
    expected = sum((step.expected_usd for step in steps), Decimal(0))
    high = sum((step.high_usd for step in steps), Decimal(0))
    capped_by: Literal["run_cap", "budget"] | None = None
    if blocked_by is not None:
        low = expected = high = Decimal(0)
    else:
        # Paid spend stops at the run's cap and at the owner's budget; free models do the rest.
        limit: Decimal = budget_remaining_usd
        limiter: Literal["run_cap", "budget"] = "budget"
        if budget_cap_usd is not None and budget_cap_usd <= limit:
            limit, limiter = budget_cap_usd, "run_cap"
        if high > limit:
            capped_by = limiter
            low, expected, high = min(low, limit), min(expected, limit), limit
    return RunEstimateOut(
        llm_policy=policy,
        low_usd=_money(low, ROUND_FLOOR),
        expected_usd=_money(expected, ROUND_HALF_UP),
        high_usd=_money(high, ROUND_CEILING),
        calls_low=sum(step.calls_low for step in steps),
        expected_calls=sum(step.calls_expected for step in steps),
        calls_high=sum(step.calls_high for step in steps),
        paid_possible=blocked_by is None,
        paid_blocked_by=blocked_by,
        paid_models_enabled=paid_models_enabled,
        budget_remaining_usd=budget_remaining_usd,
        capped_by=capped_by,
        assumptions=EstimateAssumptions(paid_chain=prices, steps=steps),
        demo=True,
    )
