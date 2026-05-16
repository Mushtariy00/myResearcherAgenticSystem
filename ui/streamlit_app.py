import streamlit as st
import sys
import os
from datetime import datetime
import time
import threading

from dotenv import load_dotenv
load_dotenv()

if os.getenv("OPENROUTER_API_KEY") and not os.getenv("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.environ["OPENROUTER_API_KEY"]
if not os.getenv("OPENAI_API_BASE"):
    os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"
if not os.getenv("OPENAI_BASE_URL"):
    os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from agentic_ai_system.supervisor_flow import ResearchSupervisorFlow, CheckpointRejected
from agentic_ai_system.models import (
    LiteratureResearchOutput, MethodStageOutput, CodingStageOutput,
    ExperimentStageOutput, WritingStageOutput, PaperFinding
)
from agentic_ai_system.run_persistence import RunPersistence
from agentic_ai_system.tools import ArxivSearchTool, SemanticScholarSearchTool

# ── Thread-based approval bridge ─────────────────────────────────────────────
import queue

_approval_event = threading.Event()
_approval_decision = {"approved": False}
_ui_update_queue = queue.Queue()  # flow thread -> UI thread

def streamlit_approval_gate(self, stage: str, preview: str) -> None:
    """Called by flow thread — pauses until Streamlit user approves/rejects."""
    _approval_event.clear()
    _approval_decision["approved"] = False

    # Push update to UI via queue (thread-safe)
    _ui_update_queue.put({
        "type": "approval_needed",
        "stage": stage,
        "preview": preview,
        "timestamp": datetime.now().isoformat(),
    })

    # Block the flow thread until the UI signals
    _approval_event.wait()

    if not _approval_decision["approved"]:
        raise CheckpointRejected(f"{stage} checkpoint rejected by user.")

ResearchSupervisorFlow._approval_gate = streamlit_approval_gate
# ─────────────────────────────────────────────────────────────────────────────

# Page config
st.set_page_config(
    page_title="Agentic Research System",
    page_icon="🔬",
    layout="wide"
)

def initialize_session_state():
    """Initialize or reset session state variables"""
    if 'flow_state' not in st.session_state:
        st.session_state.flow_state = None
    if 'flow_running' not in st.session_state:
        st.session_state.flow_running = False
    if 'current_stage' not in st.session_state:
        st.session_state.current_stage = None
    if 'approval_needed' not in st.session_state:
        st.session_state.approval_needed = False
    if 'approval_data' not in st.session_state:
        st.session_state.approval_data = None
    if 'flow_result' not in st.session_state:
        st.session_state.flow_result = None
    if 'pending_flow_instance' not in st.session_state:
        st.session_state.pending_flow_instance = None
    if 'last_completed_stages' not in st.session_state:
        st.session_state.last_completed_stages = set()

def render_sidebar():
    """Render the sidebar with configuration options"""
    with st.sidebar:
        st.header("Research Configuration")
        topic = st.text_input(
            "Research Topic", 
            value="Survey monocular depth estimation 2023-2025"
        )
        current_year = st.text_input(
            "Current Year", 
            value=str(datetime.now().year)
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Start Research", type="primary", use_container_width=True):
                if not st.session_state.flow_running:
                    initialize_session_state()
                    st.session_state.flow_running = True
                    st.session_state.current_stage = "literature"

                    flow = ResearchSupervisorFlow()
                    flow.state.topic = topic
                    flow.state.current_year = current_year
                    st.session_state.flow_state = flow

                    def run_flow():
                        try:
                            flow.kickoff(inputs={"topic": topic, "current_year": current_year})
                            st.session_state.current_stage = "completed"
                            st.session_state.flow_running = False
                        except CheckpointRejected:
                            st.session_state.current_stage = "rejected"
                            st.session_state.flow_running = False
                        except Exception as e:
                            st.session_state.flow_error = str(e)
                            st.session_state.flow_running = False

                    t = threading.Thread(target=run_flow, daemon=True)
                    t.start()
                    st.rerun()
                else:
                    st.warning("Flow is already running!")
        
        with col2:
            if st.button("🛑 Stop Flow", use_container_width=True):
                st.session_state.flow_running = False
                initialize_session_state()
                st.info("Flow stopped by user")
                st.rerun()
        
        if st.button("🗑️ Clear State", use_container_width=True):
            initialize_session_state()
            st.rerun()
        
        return topic, current_year

def render_progress_indicators():
    """Render progress indicators for research stages"""
    # Define the main research stages
    stages = ["literature", "method", "coding", "experiment", "writing"]
    stage_names = {
        "literature": "📚 Literature",
        "method": "🔬 Method", 
        "coding": "💻 Coding",
        "experiment": "🧪 Experiment",
        "writing": "📝 Writing"
    }
    
    cols = st.columns(len(stages))
    for i, stage in enumerate(stages):
        with cols[i]:
            # Check if stage is completed
            if stage in st.session_state.last_completed_stages:
                st.success(f"{stage_names[stage]} Complete")
            elif st.session_state.current_stage == stage:
                st.info(f"{stage_names[stage]} In Progress")
            else:
                st.empty()

def render_approval_section():
    if st.session_state.approval_needed and st.session_state.approval_data:
        st.warning("⚠️ **Human Approval Required**")

        stage = st.session_state.approval_data["stage"]
        st.subheader(f"Review Output for: {stage.upper()}")
        st.text_area(
            "Output to Review",
            value=st.session_state.approval_data.get("preview", ""),
            height=250,
            disabled=True,
        )

        col1, col2, _ = st.columns([1, 1, 2])
        with col1:
            if st.button("✅ Approve", type="primary", use_container_width=True):
                _approval_decision["approved"] = True
                st.session_state.approval_needed = False
                st.session_state.approval_data = None
                # Mark stage complete in UI
                st.session_state.last_completed_stages.add(stage)
                stage_order = ["literature", "method", "coding", "experiment", "writing"]
                if stage in stage_order:
                    idx = stage_order.index(stage)
                    st.session_state.current_stage = (
                        stage_order[idx + 1] if idx < len(stage_order) - 1 else "completed"
                    )
                _approval_event.set()   # unblock flow thread
                st.rerun()

        with col2:
            if st.button("❌ Reject", use_container_width=True):
                _approval_decision["approved"] = False
                st.session_state.approval_needed = False
                st.session_state.approval_data = None
                st.session_state.flow_running = False
                st.session_state.current_stage = "rejected"
                _approval_event.set()   # unblock flow thread (will raise CheckpointRejected)
                time.sleep(0.3)
                st.rerun()

def render_results_section():
    """Render the results section showing completed stage outputs"""
    st.subheader("Research Progress & Results")
    
    # Show detailed results in expanders for completed stages
    if st.session_state.flow_state and hasattr(st.session_state.flow_state, 'state'):
        state = st.session_state.flow_state.state
        
        if state.literature_output:
            with st.expander("📚 Literature Results", expanded=False):
                st.write(f"**Topic:** {state.literature_output.topic}")
                st.write(f"**Generated:** {state.literature_output.generated_at}")
                st.write("**Key Findings:**")
                for i, finding in enumerate(state.literature_output.key_findings[:5], 1):
                    st.write(f"{i}. **{finding.title}**")
                    st.write(f"   *Source:* {finding.source}")
                    st.write(f"   *Summary:* {finding.summary[:150]}...")
                    if finding.url:
                        st.write(f"   *URL:* {finding.url}")
                st.write(f"**Synthesis:** {state.literature_output.synthesis}")
        
        if state.method_output:
            with st.expander("🔬 Method Results", expanded=False):
                st.write("**Research Gaps:**")
                for gap in state.method_output.research_gaps:
                    st.write(f"- {gap}")
                st.write("")
                st.write("**Proposals:**")
                for proposal in state.method_output.proposals:
                    st.write(f"- **{proposal.name}**")
                    st.write(f"  *Rationale:* {proposal.rationale}")
                    st.write(f"  *Expected Benefit:* {proposal.expected_benefit}")
                    st.write(f"  *Risk:* {proposal.risk}")
                st.write("")
                st.write(f"**Recommended Option:** {state.method_output.recommended_option}")
                
        if state.coding_output:
            with st.expander("💻 Coding Results", expanded=False):
                st.write(f"**Sandbox Plan:** {state.coding_output.sandbox_plan}")
                st.write("")
                st.write("**Files to Create:**")
                for file in state.coding_output.files_to_create:
                    st.write(f"- {file}")
                st.write("")
                st.write("**Validation Steps:**")
                for step in state.coding_output.validation_steps:
                    st.write(f"- {step}")
                    
        if state.experiment_output:
            with st.expander("🧪 Experiment Results", expanded=False):
                st.write(f"**Experiment Goal:** {state.experiment_output.experiment_goal}")
                st.write("")
                st.write("**Run Configuration:**")
                for key, value in state.experiment_output.run_config.items():
                    st.write(f"- {key}: {value}")
                st.write("")
                st.write("**Metrics to Track:**")
                for metric in state.experiment_output.metrics_to_track:
                    st.write(f"- {metric}")
                    
        if state.writing_output:
            with st.expander("📝 Writing Results", expanded=False):
                st.write(f"**Output Format:** {state.writing_output.output_format}")
                st.write(f"**Review Focus:** {state.writing_output.review_focus}")
                st.write("")
                st.write("**Sections:**")
                for section in state.writing_output.sections:
                    st.write(f"- **{section.name}**: {section.objective}")

def render_flow_controls():
    """Render flow control buttons"""
    st.divider()
    st.subheader("Flow Control")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("⏸️ Pause Flow", use_container_width=True):
            st.session_state.flow_running = False
            _approval_decision["approved"] = False
            _approval_event.set()  # unblock thread so it can exit cleanly
            st.info("Flow paused")
            st.rerun()
    with col2:
        if st.button("🔄 Restart Flow", use_container_width=True):
            _approval_decision["approved"] = False
            _approval_event.set()  # unblock any waiting thread before reset
            initialize_session_state()
            st.rerun()
    with col3:
        if st.button("📊 View Logs", use_container_width=True):
            try:
                import sqlite3
                conn = sqlite3.connect('outputs/flow_runs.db')
                cursor = conn.cursor()
                cursor.execute("SELECT run_id, topic, status, started_at, updated_at FROM runs ORDER BY started_at DESC LIMIT 5")
                rows = cursor.fetchall()
                conn.close()

                if rows:
                    st.subheader("Recent Flow Runs")
                    for row in rows:
                        st.write(f"**ID:** {row[0][:8]}...")
                        st.write(f"**Topic:** {row[1]}")
                        st.write(f"**Status:** {row[2]}")
                        st.write(f"**Started:** {row[3]}")
                        st.write(f"**Updated:** {row[4]}")
                        st.write("---")
                else:
                    st.info("No flow runs found in database")
            except Exception as e:
                st.error(f"Could not load logs: {e}")

def render_welcome_screen():
    """Render the welcome screen when not running"""
    st.info("👈 Configure your research topic in the sidebar and click 'Start Research' to begin")
    
    st.subheader("How it works")
    st.markdown("""
    1. **Enter your research topic** in the sidebar
    2. **Click Start Research** to begin the supervised flow
    3. **Review and approve** at each checkpoint:
       - Literature search results
       - Method proposals  
       - Coding architecture plans
       - Experiment designs
       - Writing outlines
    4. **Watch the progress** as the system autonomously researches your topic
    """)
    
    st.subheader("Example Topics")
    examples = [
        "Survey monocular depth estimation 2023-2025",
        "Transformer-based models for medical image segmentation", 
        "U-Net architecture improvements in 2024",
        "Diffusion models for image generation",
        "Attention mechanisms in computer vision",
        "Federated learning for healthcare AI",
        "Neural radiance fields (NeRF) applications",
        "Self-supervised learning in computer vision"
    ]
    for example in examples:
        st.markdown(f"- {example}")

def render_footer():
    """Render the footer with status information"""
    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.session_state.flow_running:
            st.caption("🟢 Flow Status: Running")
        else:
            st.caption("⚪ Flow Status: Stopped")
    with col2:
        if st.session_state.approval_needed:
            st.caption("🟡 Waiting for Approval")
        else:
            st.caption("🟢 Ready for Input")
    with col3:
        st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}")

def main():
    """Main application function"""
    st.title("🔬 Agentic Research System")
    st.markdown("### Semi-autonomous research pipeline with human approval checkpoints")
    
    # Initialize session state
    initialize_session_state()
    
    # ── Drain thread → UI update queue ───────────────────────────────────────
    try:
        while True:
            msg = _ui_update_queue.get_nowait()
            if msg["type"] == "approval_needed":
                st.session_state.approval_needed = True
                st.session_state.approval_data = {
                    "stage": msg["stage"],
                    "preview": msg["preview"],
                    "timestamp": msg["timestamp"],
                }
                st.session_state.current_stage = msg["stage"]
    except queue.Empty:
        pass
    # ─────────────────────────────────────────────────────────────────────────

    # Render sidebar and get topic/current_year
    topic, current_year = render_sidebar()
    
    # Main content area
    if st.session_state.flow_running:
        st.header(f"Research Progress: {topic}")
        
        # Display current stage
        if st.session_state.current_stage:
            st.info(f"**Current Stage:** {st.session_state.current_stage.upper()}")
        
        # Render progress indicators
        render_progress_indicators()
        
        # Handle approval needed state
        if st.session_state.approval_needed:
            render_approval_section()
        else:
            # Show results when not waiting for approval
            render_results_section()
            
            # Show flow controls
            render_flow_controls()
    else:
        # Welcome screen when not running
        render_welcome_screen()
    
    # Render footer
    render_footer()
    
    # Auto-refresh when waiting for approval to keep UI responsive
    if st.session_state.approval_needed:
        time.sleep(0.1)
        st.rerun()

if __name__ == "__main__":
    main()