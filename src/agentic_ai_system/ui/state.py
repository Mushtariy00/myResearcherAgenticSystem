from __future__ import annotations

import streamlit as st

STAGE_ORDER = ["literature", "method", "coding", "experiment", "writing"]
STAGE_NAMES = {
    "literature": "📚 Literature",
    "method": "🔬 Method",
    "coding": "💻 Coding",
    "experiment": "🧪 Experiment",
    "writing": "📝 Writing",
}


def advance_stage(stage: str) -> None:
    if stage in STAGE_ORDER:
        st.session_state.last_completed_stages.add(stage)
        idx = STAGE_ORDER.index(stage)
        st.session_state.current_stage = (
            STAGE_ORDER[idx + 1] if idx < len(STAGE_ORDER) - 1 else "completed"
        )
    else:
        st.session_state.current_stage = stage


def initialize_session_state() -> None:
    defaults = {
        "flow_state": None,
        "flow_running": False,
        "current_stage": None,
        "flow_auto_mode": False,
        "approval_needed": False,
        "approval_data": None,
        "flow_error": None,
        "llm_error": None,
        "last_completed_stages": set(),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_session_state() -> None:
    st.session_state.flow_state = None
    st.session_state.flow_running = False
    st.session_state.current_stage = None
    st.session_state.flow_auto_mode = False
    st.session_state.approval_needed = False
    st.session_state.approval_data = None
    st.session_state.flow_error = None
    st.session_state.llm_error = None
    st.session_state.last_completed_stages = set()
