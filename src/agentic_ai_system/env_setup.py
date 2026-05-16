from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def configure_runtime_env() -> None:
    """Load project .env and map OpenRouter credentials for OpenAI-compatible clients."""
    project_root = Path(__file__).resolve().parents[2]
    env_file = project_root / ".env"
    load_dotenv(dotenv_path=env_file, override=False)

    if os.getenv("OPENROUTER_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["OPENROUTER_API_KEY"]

    if not os.getenv("OPENAI_API_BASE"):
        os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"

    if not os.getenv("OPENAI_BASE_URL"):
        os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"

