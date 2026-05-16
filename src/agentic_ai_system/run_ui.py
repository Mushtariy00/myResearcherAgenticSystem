#!/usr/bin/env python
"""Entrypoint for running the Streamlit UI."""

from pathlib import Path
import subprocess
import sys
import os


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    ui_path = project_root / "src" / "agentic_ai_system" / "ui" / "app.py"

    if not ui_path.exists():
        raise FileNotFoundError(f"Streamlit app not found at {ui_path}")

    env = os.environ.copy()
    src_path = str(project_root / "src")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src_path}:{existing_pythonpath}" if existing_pythonpath else src_path

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(ui_path),
            "--server.port",
            "8501",
            "--server.address",
            "localhost",
        ],
        env=env,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
