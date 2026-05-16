import streamlit as st
import subprocess
import sys
import os
import json
from datetime import datetime

# Add src to path so we can import our modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from agentic_ai_system.supervisor_flow import ResearchSupervisorFlow
from agentic_ai_system.main import run_flow

# Page configuration
st.set_page_config(
    page_title="Agentic Research System",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Title and description
st.title("🔬 Agentic Research System")
st.markdown("### Semi-autonomous research pipeline with human approval checkpoints")

# Sidebar for inputs
with st.sidebar:
    st.header("Research Configuration")
    topic = st.text_input(
        "Research Topic", 
        value="Survey monocular depth estimation 2023-2025",
        help="Enter the research topic to investigate"
    )
    
    current_year = st.text_input(
        "Current Year", 
        value=str(datetime.now().year),
        help="Current year for filtering recent research"
    )
    
    st.divider()
    
    # Run button
    if st.button("🚀 Start Research Flow", type="primary"):
        st.session_state.run_flow = True
        st.session_state.topic = topic
        st.session_state.current_year = current_year
        st.rerun()

# Main area
if 'run_flow' in st.session_state and st.session_state.run_flow:
    st.header("Research Flow Execution")
    
    # Create placeholders for status updates
    status_placeholder = st.empty()
    output_placeholder = st.empty()
    
    try:
        with status_placeholder.container():
            st.info("Initializing research flow...")
            
        # Run the flow in a subprocess to capture output
        # We'll use a simpler approach for now - direct integration
        inputs = {
            "topic": st.session_state.topic,
            "current_year": st.session_state.current_year
        }
        
        with status_placeholder.container():
            st.info("Running research supervisor flow...")
            
        # Import and run the flow directly
        flow = ResearchSupervisorFlow()
        
        # We need to handle the interactive nature differently for Streamlit
        # For now, let's run it and show what we can
        result = flow.kickoff(inputs=inputs)
        
        with status_placeholder.container():
            st.success("Research flow completed!")
            
        with output_placeholder.container():
            st.subheader("Flow Results")
            st.json({
                "topic": st.session_state.topic,
                "current_year": st.session_state.current_year,
                "result": str(result)[:500] + "..." if len(str(result)) > 500 else str(result)
            })
            
        # Clear the run flag
        del st.session_state.run_flow
        
    except Exception as e:
        with status_placeholder.container():
            st.error(f"Error running flow: {str(e)}")
        with output_placeholder.container():
            st.exception(e)

else:
    # Show instructions when not running
    st.info("👈 Enter your research topic in the sidebar and click 'Start Research Flow' to begin")
    
    # Show some example topics
    st.subheader("Example Research Topics")
    examples = [
        "Survey monocular depth estimation 2023-2025",
        "Transformer-based models for medical image segmentation",
        "U-Net architecture improvements in 2024",
        "Diffusion models for image generation",
        "Attention mechanisms in computer vision"
    ]
    
    for example in examples:
        st.markdown(f"- {example}")

# Footer
st.divider()
st.caption("Agentic Research System • Built with CrewAI and Streamlit")