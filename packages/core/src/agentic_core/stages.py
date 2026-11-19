"""Pipeline stages. Each stage ends with a human approval checkpoint."""

from enum import StrEnum


class Stage(StrEnum):
    LITERATURE = "literature"  # search → screen → fetch → parse → analyze → synthesize
    METHOD = "method"
    CODING = "coding"
    EXPERIMENT = "experiment"
    WRITING = "writing"


STAGE_ORDER: tuple[Stage, ...] = tuple(Stage)

# Research that needs no code or GPU (languages, education, history): the literature, a method
# for a study the researchers carry out themselves, then a draft, a review that ends in that
# proposed study. The one stage list besides a prefix of STAGE_ORDER that a run may have.
NO_CODE_STAGES: tuple[Stage, ...] = (Stage.LITERATURE, Stage.METHOD, Stage.WRITING)

# Generated code is always reviewed by a human, even when a project enables auto-approve.
NEVER_AUTO_APPROVE: frozenset[Stage] = frozenset({Stage.CODING})

# Attempts per stage in one execution of a run: the first try plus two change requests. A retry
# starts a new execution, so the stage gets MAX_ATTEMPTS more (attempt numbers keep counting).
MAX_ATTEMPTS = 3


def next_stage(stage: Stage) -> Stage | None:
    """Return the stage after ``stage``, or ``None`` when ``stage`` is the last one."""
    index = STAGE_ORDER.index(stage)
    return STAGE_ORDER[index + 1] if index + 1 < len(STAGE_ORDER) else None
