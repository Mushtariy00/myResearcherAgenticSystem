"""Payloads of the run events the worker writes (the demo seed writes the same shapes).

Payloads are i18n-friendly: codes and ids the browser translates, plus an English fallback
only where free text is unavoidable (log lines). Each builder returns (type, payload) for
``agentic_db.append_event(session, run_id, *event)``.
"""

from collections.abc import Mapping
from typing import Any

from agentic_core.contracts import EventType
from agentic_core.enums import RunStatus

type Event = tuple[EventType, dict[str, Any]]


def stage_started(stage: str, attempt: int) -> Event:
    return EventType.STAGE_STARTED, {"stage": stage, "attempt": attempt}


def run_status(status: RunStatus) -> Event:
    """The run moved between running and awaiting approval."""
    return EventType.RUN_STATUS, {"status": status.value}


def run_finished(status: RunStatus, error: str | None) -> Event:
    """The run reached its final status (or paused); ``error`` is a message code."""
    return EventType.RUN_STATUS, {"status": status.value, "error": error}


def llm_call(stage: str, call: Mapping[str, Any]) -> Event:
    """One gateway answer, as GatewayLLM recorded it."""
    return EventType.LLM_CALL, {
        "stage": stage,
        "model": call.get("model"),
        "tier": call.get("tier"),
        "cost_usd": str(call.get("cost_usd")),
        "switched_to_free": call.get("switched_to_free", False),
        "replayed": call.get("replayed", False),
    }


def stage_output_ready(stage: str, attempt: int, stage_output_id: str, degraded: bool) -> Event:
    return EventType.STAGE_OUTPUT_READY, {
        "stage": stage,
        "attempt": attempt,
        "stage_output_id": stage_output_id,
        "degraded": degraded,
    }


def stage_decided(
    *,
    stage: str,
    decision: str,
    actor_id: str,
    comment: str,
    attempt: int,
    stage_output_id: str,
    version: int,
    edited: bool,
    automatic: bool,
) -> Event:
    """A decision on ``stage_output_id``: the reviewed output, or the new version of an edit."""
    return EventType.STAGE_DECIDED, {
        "stage": stage,
        "decision": decision,
        "actor_id": actor_id,
        "comment": comment,
        "attempt": attempt,
        "stage_output_id": stage_output_id,
        "version": version,
        "edited": edited,
        "automatic": automatic,
    }


def stage_failed(stage: str, attempt: int, error: str | None) -> Event:
    return EventType.STAGE_FAILED, {"stage": stage, "attempt": attempt, "error": error}


def stage_invalidated(stage: str, attempt: int, stage_run_id: str, retry_stage: str) -> Event:
    """A retry from ``retry_stage`` made this attempt's output stale."""
    return EventType.STAGE_INVALIDATED, {
        "stage": stage,
        "attempt": attempt,
        "stage_run_id": stage_run_id,
        "retry_stage": retry_stage,
    }


def run_retried(stage: str, requested_stage: str, execution_id: str) -> Event:
    """A new workflow execution restarts the run at ``stage``.

    ``requested_stage`` is what the reviewer asked for; ``stage`` is earlier when a stage before
    it had no approved output. ``execution_id`` (the Temporal run id) makes the event unique per
    execution, so an activity retry does not record the retry twice.
    """
    return EventType.RUN_RETRIED, {
        "stage": stage,
        "requested_stage": requested_stage,
        "execution_id": execution_id,
    }


def log(stage: str, code: str, params: Mapping[str, Any], message: str) -> Event:
    """A progress line: ``code`` and ``params`` for translation, ``message`` in English."""
    return EventType.LOG, {"stage": stage, "code": code, "params": dict(params), "message": message}
