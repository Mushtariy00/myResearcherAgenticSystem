from __future__ import annotations

import ast
import json
import re
from time import sleep
from typing import Any, TypeVar

import json5
from pydantic import BaseModel

from agentic_ai_system.orchestration.exceptions import CheckpointRejected

ModelT = TypeVar("ModelT", bound=BaseModel)


def run_id(flow: Any) -> str:
    return str(getattr(flow.state, "id", "unknown"))


def kickoff_with_retry(flow: Any, stage: str, agent: Any, prompt: str, attempts: int = 3) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            if attempt > 1:
                flow._persistence.stage_event(
                    run_id(flow),
                    stage,
                    "retry",
                    f"Retry attempt {attempt}/{attempts}",
                )
            return agent.kickoff(prompt)
        except Exception as exc:
            last_error = exc
            flow._persistence.stage_event(
                run_id(flow),
                stage,
                "error",
                f"LLM kickoff failed attempt {attempt}: {exc}",
            )
            if attempt < attempts:
                sleep(min(2 ** (attempt - 1), 4))
    raise RuntimeError(f"{stage} failed after {attempts} attempts: {last_error}")


def extract_json_candidate(raw_output: str) -> str:
    fenced_match = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        raw_output,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if fenced_match:
        return fenced_match.group(1)

    start_idx = raw_output.find("{")
    if start_idx == -1:
        raise RuntimeError("No JSON object start token found in model output.")

    in_string = False
    escape = False
    depth = 0
    for index in range(start_idx, len(raw_output)):
        char = raw_output[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
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
                return raw_output[start_idx : index + 1]

    raise RuntimeError("No complete JSON object found in model output.")


def parse_model_output(raw_output: str, model: type[ModelT]) -> ModelT:
    payload_text = extract_json_candidate(raw_output)
    cleaned_payload = re.sub(r"[\x00-\x1f]", " ", payload_text)

    payload = None
    for candidate in (payload_text, cleaned_payload):
        try:
            payload = json.loads(candidate)
            break
        except json.JSONDecodeError:
            try:
                payload = json5.loads(candidate)
                if isinstance(payload, dict):
                    break
            except Exception:
                payload = None
            try:
                literal_payload = ast.literal_eval(candidate)
                if isinstance(literal_payload, dict):
                    payload = literal_payload
                    break
            except (SyntaxError, ValueError):
                continue

    if payload is None:
        raise RuntimeError(
            f"{model.__name__} stage output was not valid JSON. "
            f"Snippet: {cleaned_payload[:240]}"
        )

    return model.model_validate(payload)


def approval_gate(flow: Any, stage: str, preview: str) -> None:
    if getattr(flow.state, "auto_mode", False):
        flow.state.approvals[stage] = True
        flow._persistence.log_approval(run_id(flow), stage, True)
        return
    print(f"\n=== {stage.upper()} CHECKPOINT ===")
    print(preview)
    answer = input("\nApprove and continue? [y/N]: ").strip().lower()
    approved = answer in {"y", "yes"}
    flow.state.approvals[stage] = approved
    flow._persistence.log_approval(run_id(flow), stage, approved)
    if not approved:
        raise CheckpointRejected(f"{stage} checkpoint was rejected by user.")
