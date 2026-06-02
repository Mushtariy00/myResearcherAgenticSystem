from __future__ import annotations

import queue
import time
import streamlit as st

from agentic_ai_system.env_setup import configure_runtime_env
from agentic_ai_system.ui.bridge import ui_update_queue
from agentic_ai_system.ui.components import (
    render_approval_section,
    render_flow_controls,
    render_footer,
    render_progress_indicators,
    render_results_section,
    render_sidebar,
    render_welcome_screen,
)
from agentic_ai_system.ui.runtime import patch_flow_for_streamlit
from agentic_ai_system.ui.state import advance_stage, initialize_session_state

configure_runtime_env()

st.set_page_config(page_title="Agentic Research System", page_icon="🔬", layout="wide")


def process_ui_events() -> None:
    try:
        while True:
            msg = ui_update_queue.get_nowait()
            msg_type = msg.get("type")
            if msg_type == "approval_needed":
                st.session_state.approval_needed = True
                st.session_state.approval_data = {
                    "stage": msg["stage"],
                    "preview": msg["preview"],
                    "timestamp": msg["timestamp"],
                }
                st.session_state.current_stage = msg["stage"]
            elif msg_type == "flow_completed":
                st.session_state.current_stage = "completed"
                st.session_state.flow_running = False
                st.session_state.approval_needed = False
                st.session_state.approval_data = None
            elif msg_type == "flow_stopped":
                st.session_state.current_stage = "rejected"
                st.session_state.flow_running = False
                st.session_state.approval_needed = False
                st.session_state.approval_data = None
                st.session_state.flow_error = msg.get("reason", "Flow stopped.")
            elif msg_type == "flow_error":
                st.session_state.current_stage = "failed"
                st.session_state.flow_running = False
                st.session_state.approval_needed = False
                st.session_state.approval_data = None
                st.session_state.flow_error = msg.get("error", "Unknown flow error.")
            elif msg_type == "stage_completed":
                advance_stage(msg["stage"])
    except queue.Empty:
        pass


def main() -> None:
    patch_flow_for_streamlit()
    initialize_session_state()
    process_ui_events()
    if st.session_state.approval_needed and not st.session_state.approval_data:
        st.session_state.approval_needed = False

    st.title("🔬 Agentic Research System")
    st.markdown("### Semi-autonomous research pipeline with human approval checkpoints")

    topic, _, _ = render_sidebar()

    if st.session_state.flow_running:
        st.header(f"Research Progress: {topic}")
        if st.session_state.current_stage:
            st.info(f"**Current Stage:** {st.session_state.current_stage.upper()}")

        render_progress_indicators()
        if st.session_state.approval_needed:
            render_approval_section()
        else:
            render_results_section()
        render_flow_controls()
    elif st.session_state.approval_needed and st.session_state.approval_data:
        st.header("Approval Required")
        render_approval_section()
        render_results_section()
        render_flow_controls()
    else:
        if st.session_state.flow_state is None:
            render_welcome_screen()
        if st.session_state.flow_error:
            st.error(st.session_state.flow_error)
        render_results_section()
        render_flow_controls()

    render_footer()
    if st.session_state.flow_running or st.session_state.approval_needed:
        time.sleep(0.3)
        st.rerun()


if __name__ == "__main__":
    main()
