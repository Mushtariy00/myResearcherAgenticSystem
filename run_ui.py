#!/usr/bin/env python
"""
Entry point for running the Agentic Research System Streamlit UI.
"""
import subprocess
import sys
import os

def main():
    """Run the Streamlit UI."""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ui_path = os.path.join(script_dir, "ui", "streamlit_app.py")
    
    # Run streamlit
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", ui_path,
        "--server.port", "8501",
        "--server.address", "localhost"
    ])

if __name__ == "__main__":
    main()