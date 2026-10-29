import pytest
from pydantic import ValidationError

from agentic_core.schemas import LiteratureOutput, MethodOutput

VALID_LITERATURE = {
    "topic": "Monocular depth estimation 2023-2025",
    "key_findings": [
        {
            "title": "Depth Anything V2",
            "source": "arXiv",
            "summary": "Synthetic labels plus a large teacher improve fine detail.",
            "url": "https://arxiv.org/abs/2406.09414",
        }
    ],
    "synthesis": "Foundation models dominate zero-shot relative depth.",
}


def test_valid_literature_output_passes() -> None:
    output = LiteratureOutput.model_validate(VALID_LITERATURE)
    assert output.key_findings[0].title == "Depth Anything V2"


def test_empty_llm_answer_is_rejected() -> None:
    # The legacy schemas accepted {} because every field had a default.
    with pytest.raises(ValidationError):
        LiteratureOutput.model_validate({})
    with pytest.raises(ValidationError):
        MethodOutput.model_validate({})


def test_blank_strings_and_empty_lists_are_rejected() -> None:
    with pytest.raises(ValidationError):
        LiteratureOutput.model_validate({**VALID_LITERATURE, "synthesis": "   "})
    with pytest.raises(ValidationError):
        LiteratureOutput.model_validate({**VALID_LITERATURE, "key_findings": []})


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        LiteratureOutput.model_validate({**VALID_LITERATURE, "confidence": 0.9})
