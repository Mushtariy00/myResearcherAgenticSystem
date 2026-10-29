from __future__ import annotations

from datetime import datetime
import sqlite3
from pathlib import Path

import streamlit as st

from agentic_ai_system.ui.bridge import approval_decision, approval_event
from agentic_ai_system.ui.runtime import resume_from_stage, start_flow
from agentic_ai_system.ui.state import STAGE_NAMES, STAGE_ORDER, advance_stage, reset_session_state


def render_sidebar() -> tuple[str, str, bool]:
    with st.sidebar:
        st.header("Research Configuration")
        topic = st.text_input("Research Topic", value="Survey monocular depth estimation 2023-2025")
        current_year = st.text_input("Current Year", value=str(datetime.now().year))
        auto_mode = st.checkbox(
            "Auto mode",
            value=st.session_state.flow_auto_mode,
            help="Skip approval prompts and continue to the next stage automatically.",
        )
        st.session_state.flow_auto_mode = auto_mode

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Start Research", type="primary", use_container_width=True):
                if st.session_state.flow_running:
                    st.warning("Flow is already running.")
                else:
                    start_flow(topic, current_year, auto_mode=auto_mode)
                    st.rerun()
        with col2:
            if st.button("🛑 Stop Flow", use_container_width=True):
                approval_decision["approved"] = False
                approval_event.set()
                reset_session_state()
                st.info("Flow stopped.")
                st.rerun()

        if st.button("🗑️ Clear State", use_container_width=True):
            reset_session_state()
            st.rerun()

    return topic, current_year, auto_mode


def render_progress_indicators() -> None:
    if st.session_state.llm_error:
        err = st.session_state.llm_error
        st.warning(
            f"⚠️ **LLM Retry in Progress** ({err['stage'].upper()})\n\n"
            f"Attempt {err['attempt']}/{err['total_attempts']} failed. "
            f"Retrying in {err['delay']}s...\n\n"
            f"*Error: {err['error']}*"
        )

    cols = st.columns(len(STAGE_ORDER))
    for index, stage in enumerate(STAGE_ORDER):
        with cols[index]:
            if stage in st.session_state.last_completed_stages:
                st.success(f"{STAGE_NAMES[stage]} Complete")
            elif st.session_state.current_stage == stage:
                st.info(f"{STAGE_NAMES[stage]} In Progress")
            else:
                st.empty()


def render_approval_section() -> None:
    if not (st.session_state.approval_needed and st.session_state.approval_data):
        return

    stage = st.session_state.approval_data["stage"]
    st.warning("⚠️ Human approval required")
    st.subheader(f"Review Output: {stage.upper()}")
    st.text_area(
        "Output to review",
        value=st.session_state.approval_data.get("preview", ""),
        height=260,
        disabled=True,
    )

    col1, col2, _ = st.columns([1, 1, 2])
    with col1:
        if st.button("✅ Approve", type="primary", use_container_width=True):
            approval_decision["approved"] = True
            st.session_state.approval_needed = False
            st.session_state.approval_data = None
            advance_stage(stage)
            approval_event.set()
            st.rerun()
    with col2:
        if st.button("❌ Reject", use_container_width=True):
            approval_decision["approved"] = False
            st.session_state.approval_needed = False
            st.session_state.approval_data = None
            st.session_state.flow_running = False
            st.session_state.current_stage = "rejected"
            approval_event.set()
            st.rerun()


def render_results_section() -> None:
    st.subheader("Research Progress & Results")
    flow = st.session_state.flow_state
    if not (flow and hasattr(flow, "state")):
        return
    state = flow.state

    if state.literature_output:
        with st.expander("📚 Literature Results", expanded=False):
            st.write(f"**Topic:** {state.literature_output.topic}")
            st.write(f"**Generated:** {state.literature_output.generated_at}")
            st.write("**Key Findings:**")
            for idx, finding in enumerate(state.literature_output.key_findings[:5], 1):
                st.write(f"{idx}. **{finding.title}**")
                st.write(f"   *Source:* {finding.source}")
                st.write(f"   *Summary:* {finding.summary[:150]}...")
                if finding.url:
                    st.write(f"   *URL:* {finding.url}")
            st.write(f"**Synthesis:** {state.literature_output.synthesis}")
            if getattr(state, "literature_screen_output", None):
                st.write("**Selected Indices:**")
                st.write(f"- {state.literature_screen_output.selected_indices}")
                st.write(f"**Screen Rationale:** {state.literature_screen_output.selection_rationale}")
            if getattr(state, "literature_screen_path", ""):
                st.write(f"**Screening Artifact:** `{state.literature_screen_path}`")
            if getattr(state, "literature_manifest_path", ""):
                st.write(f"**Artifact Manifest:** `{state.literature_manifest_path}`")
            if getattr(state, "literature_fetch_dir", ""):
                st.write(f"**Full Text Directory:** `{state.literature_fetch_dir}`")
            if getattr(state, "literature_fetch_manifest_path", ""):
                st.write(f"**Full Text Manifest:** `{state.literature_fetch_manifest_path}`")
            if getattr(state, "literature_analysis_manifest_path", ""):
                st.write(f"**Paper Analysis Manifest:** `{state.literature_analysis_manifest_path}`")

    if state.method_output:
        with st.expander("🔬 Method Results", expanded=False):
            st.write("**Research Gaps:**")
            for gap in state.method_output.research_gaps:
                st.write(f"- {gap}")
            st.write("**Proposals:**")
            for proposal in state.method_output.proposals:
                st.write(f"- **{proposal.name}**")
                st.write(f"  *Rationale:* {proposal.rationale}")
                st.write(f"  *Expected Benefit:* {proposal.expected_benefit}")
                st.write(f"  *Risk:* {proposal.risk}")
            st.write(f"**Recommended Option:** {state.method_output.recommended_option}")
            if getattr(state, "method_artifact_path", ""):
                st.write(f"**Artifact File:** `{state.method_artifact_path}`")
            if getattr(state, "method_manifest_path", ""):
                st.write(f"**Artifact Manifest:** `{state.method_manifest_path}`")

    if state.coding_output:
        with st.expander("💻 Coding Results", expanded=False):
            st.write(f"**Sandbox Plan:** {state.coding_output.sandbox_plan}")
            st.write("**Files to Create:**")
            for file in state.coding_output.files_to_create:
                st.write(f"- {file}")
            st.write("**Validation Steps:**")
            for step in state.coding_output.validation_steps:
                st.write(f"- {step}")
            if state.coding_execution:
                st.write(f"**Sandbox Directory:** `{state.coding_execution.sandbox_dir}`")
                st.write(
                    f"**Created Files:** {len(state.coding_execution.created_files)} | "
                    f"**Validated Python Files:** {len(state.coding_execution.validated_files)}"
                )
                if state.coding_execution.validation_errors:
                    st.write("**Validation Errors:**")
                    for error in state.coding_execution.validation_errors:
                        st.write(f"- {error}")
                if state.coding_execution.created_files:
                    st.write("**Created File Contents:**")
                    for path in state.coding_execution.created_files:
                        st.code(Path(path).read_text(encoding="utf-8"), language="python" if path.endswith(".py") else None)
                if getattr(state, "coding_manifest_path", ""):
                    st.write(f"**Artifact Manifest:** `{state.coding_manifest_path}`")

    if state.experiment_output:
        with st.expander("🧪 Experiment Results", expanded=False):
            st.write(f"**Experiment Goal:** {state.experiment_output.experiment_goal}")
            st.write("**Run Configuration:**")
            for key, value in state.experiment_output.run_config.items():
                st.write(f"- {key}: {value}")
            st.write("**Metrics to Track:**")
            for metric in state.experiment_output.metrics_to_track:
                st.write(f"- {metric}")
            if state.experiment_execution:
                st.write(f"**Run Directory:** `{state.experiment_execution.run_dir}`")
                st.write(f"**Summary File:** `{state.experiment_execution.summary_file}`")
                st.write("**Captured Metrics:**")
                for key, value in state.experiment_execution.metrics.items():
                    st.write(f"- {key}: {value}")
            if getattr(state, "experiment_manifest_path", ""):
                st.write(f"**Artifact Manifest:** `{state.experiment_manifest_path}`")

    if state.writing_output:
        with st.expander("📝 Writing Results", expanded=False):
            st.write(f"**Output Format:** {state.writing_output.output_format}")
            st.write(f"**Review Focus:** {state.writing_output.review_focus}")
            st.write("**Sections:**")
            for section in state.writing_output.sections:
                st.write(f"- **{section.name}**: {section.objective}")
            if state.writing_artifact_dir:
                st.write(f"**Artifact Directory:** `{state.writing_artifact_dir}`")
            if state.writing_artifact_files:
                st.write("**Generated Draft Files:**")
                for path in state.writing_artifact_files:
                    st.write(f"- `{path}`")
            if getattr(state, "writing_manifest_path", ""):
                st.write(f"**Artifact Manifest:** `{state.writing_manifest_path}`")


def render_flow_controls() -> None:
    st.divider()
    st.subheader("Flow Control")
    flow_running = st.session_state.flow_running
    flow_state = st.session_state.flow_state
    approved_stages = set()
    if flow_state is not None and hasattr(flow_state, "state"):
        approved_stages = {
            stage for stage, approved in flow_state.state.approvals.items() if approved
        }
    completed_stages = set(st.session_state.last_completed_stages)
    if approved_stages:
        completed_stages = completed_stages.union(approved_stages)
    if flow_state is not None and hasattr(flow_state, "state"):
        state = flow_state.state
        if state.literature_output:
            completed_stages.add("literature")
        if state.method_output:
            completed_stages.add("method")
        if state.coding_output:
            completed_stages.add("coding")
        if state.experiment_output:
            completed_stages.add("experiment")
        if state.writing_output:
            completed_stages.add("writing")
    last_completed_index = max(
        (STAGE_ORDER.index(stage) for stage in completed_stages if stage in STAGE_ORDER),
        default=-1,
    )
    resume_options = (
        STAGE_ORDER[last_completed_index + 1 :] if last_completed_index + 1 < len(STAGE_ORDER) else []
    )
    show_resume_controls = (
        flow_state is not None
        and (
            st.session_state.current_stage in {"rejected", "failed"}
            or (not flow_running and completed_stages)
            or (not flow_running and st.session_state.flow_error)
            or (
                st.session_state.current_stage == "completed"
                and st.session_state.flow_auto_mode
            )
        )
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        if flow_running:
            if st.button("⏸️ Pause Flow", use_container_width=True):
                st.session_state.flow_running = False
                approval_decision["approved"] = False
                approval_event.set()
                st.info("Flow paused.")
                st.rerun()
        elif show_resume_controls and resume_options:
            resume_disabled = st.session_state.approval_needed
            resume_choice = st.selectbox(
                "Resume from",
                options=resume_options,
                format_func=lambda stage: STAGE_NAMES.get(stage, stage),
                disabled=resume_disabled,
                key="resume_stage",
            )
            if st.button("▶️ Resume", use_container_width=True, disabled=resume_disabled):
                resume_from_stage(resume_choice, auto_mode=st.session_state.flow_auto_mode)
                st.rerun()
    with col2:
        if st.button("🔄 Restart Flow", use_container_width=True):
            approval_decision["approved"] = False
            approval_event.set()
            reset_session_state()
            st.rerun()
    with col3:
        if st.button("📊 View Logs", use_container_width=True):
            try:
                conn = sqlite3.connect("outputs/flow_runs.db")
                rows = conn.execute(
                    "SELECT run_id, topic, status, started_at, updated_at "
                    "FROM runs ORDER BY started_at DESC LIMIT 5"
                ).fetchall()
                conn.close()
                if not rows:
                    st.info("No flow runs found.")
                else:
                    st.subheader("Recent Flow Runs")
                    for row in rows:
                        st.write(f"**ID:** {row[0][:8]}...")
                        st.write(f"**Topic:** {row[1]}")
                        st.write(f"**Status:** {row[2]}")
                        st.write(f"**Started:** {row[3]}")
                        st.write(f"**Updated:** {row[4]}")
                        st.write("---")
            except Exception as error:
                st.error(f"Could not load logs: {error}")


def render_welcome_screen() -> None:
    st.info("👈 Configure your research topic in the sidebar and click Start Research.")
    st.subheader("How it works")
    st.markdown(
        """
1. Enter your research topic.
2. Start the supervised flow.
3. Review and approve each checkpoint:
   - Literature
   - Method
   - Coding
   - Experiment
   - Writing
4. Review stage outputs and persisted logs.
"""
    )


def render_footer() -> None:
    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption("🟢 Flow Running" if st.session_state.flow_running else "⚪ Flow Stopped")
    with col2:
        st.caption("🟡 Waiting for Approval" if st.session_state.approval_needed else "🟢 Ready")
    with col3:
        st.caption(
            "Student: ABDURAKHMONOVA MUSHTARIY MAVLONBERDI KIZI | "
            "Class: Cloud Computing (09170_001) [이영호] | "
            "ID: 202640379 | "
            "Email: dil1977@gachon.ac.kr"
        )
    st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
