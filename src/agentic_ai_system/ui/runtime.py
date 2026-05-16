from __future__ import annotations

from datetime import datetime
import threading

import streamlit as st

from agentic_ai_system.supervisor_flow import CheckpointRejected, ResearchSupervisorFlow
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
        if not approval_decision["approved"]:
            raise CheckpointRejected(f"{stage} checkpoint rejected by user.")

    ResearchSupervisorFlow._approval_gate = streamlit_approval_gate  # type: ignore[assignment]
    ResearchSupervisorFlow._streamlit_patched = True  # type: ignore[attr-defined]


def start_flow(topic: str, current_year: str) -> None:
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
    st.session_state.flow_state = flow

    def run_flow_thread() -> None:
        try:
            flow.kickoff(inputs={"topic": topic, "current_year": current_year})
            ui_update_queue.put({"type": "flow_completed"})
        except CheckpointRejected as error:
            ui_update_queue.put({"type": "flow_stopped", "reason": str(error)})
        except Exception as error:
            ui_update_queue.put({"type": "flow_error", "error": str(error)})

    worker = threading.Thread(target=run_flow_thread, daemon=True)
    worker.start()

