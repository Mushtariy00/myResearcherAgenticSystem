#!/usr/bin/env python
import sys
from datetime import datetime

from agentic_ai_system.env_setup import configure_runtime_env
from agentic_ai_system.orchestration.supervisor_flow import CheckpointRejected, ResearchSupervisorFlow

configure_runtime_env()

def run_flow():
    """
    Run the CLI-first supervisor flow with checkpoints.
    """
    topic = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else "AI LLMs"
    inputs = {
        "topic": topic,
        "current_year": str(datetime.now().year)
    }

    try:
        return ResearchSupervisorFlow().kickoff(inputs=inputs)
    except CheckpointRejected as e:
        print(f"Flow stopped by user: {e}")
        return 0
    except Exception as e:
        raise Exception(f"An error occurred while running the supervisor flow: {e}")


def run() -> int:
    return run_flow()
