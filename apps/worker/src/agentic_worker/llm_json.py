"""Pull a JSON object out of free-form model text, then validate it strictly.

Ported from main:src/agentic_ai_system/orchestration/flow_utils.py (extract_json_candidate,
parse_model_output): fenced block → first balanced {...} → json → json5 → Python literal.
"""

import ast
import json
import re
from typing import Any

import json5
from pydantic import BaseModel

_FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


class InvalidModelOutputError(ValueError):
    """The model's answer is not a JSON object matching the schema."""


def extract_json_candidate(raw: str) -> str:
    fenced = _FENCED.search(raw)
    if fenced:
        return fenced.group(1)
    start = raw.find("{")
    if start == -1:
        raise InvalidModelOutputError("no JSON object in the model output")
    depth, in_string, escaped = 0, False, False
    for index in range(start, len(raw)):
        char = raw[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return raw[start : index + 1]
    raise InvalidModelOutputError("unterminated JSON object in the model output")


def _load(candidate: str) -> dict[str, Any]:
    cleaned = re.sub(r"[\x00-\x1f]", " ", candidate)
    for text in (candidate, cleaned):
        for loader in (json.loads, json5.loads, ast.literal_eval):
            try:
                value = loader(text)
            except (ValueError, SyntaxError, TypeError, RecursionError):
                continue
            if isinstance(value, dict):
                return value
    raise InvalidModelOutputError(f"not valid JSON: {cleaned[:200]}")


def parse_model_output[ModelT: BaseModel](raw: str, model: type[ModelT]) -> ModelT:
    data = _load(extract_json_candidate(raw))
    try:
        return model.model_validate(data)
    except ValueError as exc:  # pydantic.ValidationError is a ValueError
        raise InvalidModelOutputError(str(exc)) from exc
