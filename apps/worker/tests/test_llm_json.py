import pytest

from agentic_worker.llm_json import (
    InvalidModelOutputError,
    extract_json_candidate,
    parse_model_output,
)
from agentic_worker.stages import ResearchPlan

PLAN = (
    '{"topic": "Depth", "queries": ["a", "b", "c"], "scope": "s", '
    '"inclusion_criteria": ["x"], "subtopics": ["y"]}'
)


def test_fenced_json_wins_over_surrounding_prose() -> None:
    raw = f"Thought: done.\nFinal Answer:\n```json\n{PLAN}\n```\nHope this helps!"
    assert extract_json_candidate(raw) == PLAN


def test_first_balanced_object_is_used_and_braces_in_strings_are_ignored() -> None:
    raw = 'Here: {"scope": "a } b", "n": {"x": 1}} trailing {"other": 2}'
    assert extract_json_candidate(raw) == '{"scope": "a } b", "n": {"x": 1}}'


def test_json5_style_answers_from_free_models_are_accepted() -> None:
    raw = (
        "{topic: 'Depth', queries: ['a','b','c',], scope: 's', "
        "inclusion_criteria: ['x'], subtopics: ['y'],}"
    )
    assert parse_model_output(raw, ResearchPlan).queries == ["a", "b", "c"]


def test_schema_violations_are_errors_not_silent_defaults() -> None:
    with pytest.raises(InvalidModelOutputError):
        parse_model_output('{"topic": "Depth", "queries": ["only one"]}', ResearchPlan)
    with pytest.raises(InvalidModelOutputError):
        parse_model_output("I could not find anything.", ResearchPlan)
