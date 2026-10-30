"""Pipeline stages. Each stage ends with a human approval checkpoint."""

from enum import StrEnum


class Stage(StrEnum):
    LITERATURE = "literature"  # search → screen → fetch → parse → analyze → synthesize
    METHOD = "method"
    CODING = "coding"
    EXPERIMENT = "experiment"
    WRITING = "writing"


STAGE_ORDER: tuple[Stage, ...] = tuple(Stage)

# Generated code is always reviewed by a human, even when a project enables auto-approve.
NEVER_AUTO_APPROVE: frozenset[Stage] = frozenset({Stage.CODING})

# Attempts per stage in one execution of a run: the first try plus two change requests. A retry
# starts a new execution, so the stage gets MAX_ATTEMPTS more (attempt numbers keep counting).
MAX_ATTEMPTS = 3


def next_stage(stage: Stage) -> Stage | None:
    """Return the stage after ``stage``, or ``None`` when ``stage`` is the last one."""
    index = STAGE_ORDER.index(stage)
    return STAGE_ORDER[index + 1] if index + 1 < len(STAGE_ORDER) else None
