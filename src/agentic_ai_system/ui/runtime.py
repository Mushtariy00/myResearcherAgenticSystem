from __future__ import annotations

from datetime import datetime
from pathlib import Path
import threading

import streamlit as st

from agentic_ai_system.orchestration.supervisor_flow import CheckpointRejected, ResearchSupervisorFlow
from agentic_ai_system.orchestration.research_pipeline import (
    check_coding_prereqs,
    run_coding_stage,
    run_experiment_stage_flow,
    run_method_stage,
    run_writing_stage,
)
from agentic_ai_system.ui.state import STAGE_ORDER
from agentic_ai_system.ui.bridge import (
    approval_decision,
    approval_event,
    clear_ui_queue,
    ui_update_queue,
)


def patch_flow_for_streamlit() -> None:
    if getattr(ResearchSupervisorFlow, "_streamlit_patched", False):
        return

    def streamlit_approval_gate(self, stage: str, preview: str) -> None:
        auto_mode = getattr(self.state, "auto_mode", False)
        if hasattr(st.session_state, "flow_auto_mode"):
            auto_mode = bool(st.session_state.flow_auto_mode)
        if auto_mode:
            approval_decision["approved"] = True
            self.state.approvals[stage] = True
            self._persistence.log_approval(self._run_id(), stage, True)
            return
        approval_event.clear()
        approval_decision["approved"] = False
        ui_update_queue.put(
            {
                "type": "approval_needed",
                "stage": stage,
                "preview": preview,
                "timestamp": datetime.now().isoformat(),
            }
        )
        approval_event.wait()
        approved = bool(approval_decision["approved"])
        self.state.approvals[stage] = approved
        self._persistence.log_approval(self._run_id(), stage, approved)
        if not approved:
            raise CheckpointRejected(f"{stage} checkpoint rejected by user.")

    ResearchSupervisorFlow._approval_gate = streamlit_approval_gate  # type: ignore[assignment]
    ResearchSupervisorFlow._streamlit_patched = True  # type: ignore[attr-defined]


def start_flow(topic: str, current_year: str, auto_mode: bool = False) -> None:
    patch_flow_for_streamlit()
    clear_ui_queue()
    st.session_state.flow_running = True
    st.session_state.current_stage = "literature"
    st.session_state.flow_error = None
    st.session_state.approval_needed = False
    st.session_state.approval_data = None
    st.session_state.last_completed_stages = set()

    flow = ResearchSupervisorFlow()
    flow.state.topic = topic
    flow.state.current_year = current_year
    flow.state.auto_mode = auto_mode
    st.session_state.flow_state = flow

    def run_flow_thread() -> None:
        try:
            flow.kickoff(inputs={"topic": topic, "current_year": current_year, "auto_mode": auto_mode})
            ui_update_queue.put({"type": "flow_completed"})
        except CheckpointRejected as error:
            ui_update_queue.put({"type": "flow_stopped", "reason": str(error)})
        except Exception as error:
            ui_update_queue.put({"type": "flow_error", "error": str(error)})

    worker = threading.Thread(target=run_flow_thread, daemon=True)
    worker.start()


def _require_prior_approvals(flow: ResearchSupervisorFlow, stage: str) -> None:
    if stage not in STAGE_ORDER:
        raise ValueError(f"Unknown stage: {stage}")
    prior_stages = STAGE_ORDER[: STAGE_ORDER.index(stage)]
    for prior in prior_stages:
        if not flow.state.approvals.get(prior):
            raise ValueError(f"Cannot resume: {prior} stage is not approved.")


def resume_from_stage(stage: str, auto_mode: bool = False) -> None:
    flow = st.session_state.flow_state
    if flow is None:
        st.session_state.flow_error = "No existing flow state to resume."
        return
    try:
        _require_prior_approvals(flow, stage)
    except ValueError as error:
        st.session_state.flow_error = str(error)
        return

    if stage == "method":
        if not flow.state.literature_output:
            st.session_state.flow_error = "Cannot resume: literature output is missing."
            return
    elif stage == "coding":
        if not flow.state.method_output:
            st.session_state.flow_error = "Cannot resume: method stage output is missing."
            return
        ok, messages = check_coding_prereqs(Path.cwd())
        if not ok:
            st.session_state.flow_error = "Resume blocked: " + " ".join(messages)
            return
    elif stage == "experiment":
        if not flow.state.coding_output:
            st.session_state.flow_error = "Cannot resume: coding stage output is missing."
            return
        if flow.state.coding_execution is None:
            st.session_state.flow_error = "Cannot resume: coding execution artifacts are missing."
            return
    elif stage == "writing":
        if not flow.state.experiment_output:
            st.session_state.flow_error = "Cannot resume: experiment stage output is missing."
            return
        if flow.state.experiment_execution is None:
            st.session_state.flow_error = "Cannot resume: experiment execution artifacts are missing."
            return
    else:
        st.session_state.flow_error = f"Unsupported resume stage: {stage}"
        return

    clear_ui_queue()
    st.session_state.flow_running = True
    st.session_state.current_stage = stage
    st.session_state.flow_error = None
    st.session_state.approval_needed = False
    st.session_state.approval_data = None
    flow.state.auto_mode = auto_mode

    def run_flow_thread() -> None:
        try:
            if stage == "method":
                method_output = run_method_stage(flow, flow.state.literature_output)
                coding_output = run_coding_stage(flow, method_output)
                experiment_output = run_experiment_stage_flow(flow, coding_output)
                run_writing_stage(flow, experiment_output)
            elif stage == "coding":
                coding_output = run_coding_stage(flow, flow.state.method_output)
                experiment_output = run_experiment_stage_flow(flow, coding_output)
                run_writing_stage(flow, experiment_output)
            elif stage == "experiment":
                experiment_output = run_experiment_stage_flow(flow, flow.state.coding_output)
                run_writing_stage(flow, experiment_output)
            elif stage == "writing":
                run_writing_stage(flow, flow.state.experiment_output)
            ui_update_queue.put({"type": "flow_completed"})
        except CheckpointRejected as error:
            ui_update_queue.put({"type": "flow_stopped", "reason": str(error)})
        except Exception as error:
            ui_update_queue.put({"type": "flow_error", "error": str(error)})

    worker = threading.Thread(target=run_flow_thread, daemon=True)
    worker.start()
