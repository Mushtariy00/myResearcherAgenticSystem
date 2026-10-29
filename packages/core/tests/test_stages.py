from agentic_core import NEVER_AUTO_APPROVE, STAGE_ORDER, Stage, next_stage


def test_stage_order_matches_pipeline() -> None:
    assert [s.value for s in STAGE_ORDER] == [
        "literature",
        "method",
        "coding",
        "experiment",
        "writing",
    ]


def test_next_stage_walks_the_pipeline_and_ends() -> None:
    assert next_stage(Stage.LITERATURE) is Stage.METHOD
    assert next_stage(Stage.EXPERIMENT) is Stage.WRITING
    assert next_stage(Stage.WRITING) is None


def test_coding_is_never_auto_approved() -> None:
    assert Stage.CODING in NEVER_AUTO_APPROVE
