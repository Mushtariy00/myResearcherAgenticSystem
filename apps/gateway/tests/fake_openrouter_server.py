"""A stand-in for OpenRouter's API for local end-to-end runs and E2E tests (no quota, no cost).

Run:  uv run uvicorn fake_openrouter_server:app --app-dir apps/gateway/tests --port 8199
Then point the gateway at it:  ARP_OPENROUTER_BASE_URL=http://127.0.0.1:8199/api/v1
"""

import json
import re
import uuid
from typing import Any

from fastapi import FastAPI, Request

app = FastAPI(title="Fake OpenRouter")

FREE_MODEL = "fake/research-planner:free"
PAID_MODEL = "fake/research-planner-pro"


@app.get("/api/v1/models")
async def models() -> dict[str, Any]:
    text = {"input_modalities": ["text"], "output_modalities": ["text"]}
    return {
        "data": [
            {"id": FREE_MODEL, "pricing": {"prompt": "0", "completion": "0"}, "context_length": 64_000, "architecture": text},
            {
                "id": PAID_MODEL,
                "pricing": {"prompt": "0.0000005", "completion": "0.0000015"},
                "context_length": 128_000,
                "architecture": text,
            },
        ]
    }


def _topic(messages: list[dict[str, Any]]) -> str:
    joined = "\n".join(str(m.get("content", "")) for m in messages)
    match = re.search(r"research topic:\s*(.+)", joined)
    return match.group(1).strip() if match else "the requested topic"


@app.post("/api/v1/chat/completions")
async def chat(request: Request) -> dict[str, Any]:
    body = await request.json()
    topic = _topic(body.get("messages", []))
    plan = {
        "topic": topic,
        "queries": [f"{topic} survey", f"{topic} benchmark", f"{topic} self-supervised"],
        "scope": f"Recent peer-reviewed and arXiv work on {topic}; excludes non-English sources.",
        "inclusion_criteria": ["Published 2023 or later", "Reports quantitative results"],
        "subtopics": ["Datasets", "Architectures", "Evaluation metrics"],
    }
    # CrewAI agents expect the ReAct "Final Answer:" format when no tools are used.
    content = f"Thought: I now know the final answer\nFinal Answer: ```json\n{json.dumps(plan)}\n```"
    model = body.get("model", FREE_MODEL)
    paid = not str(model).endswith(":free")
    return {
        "id": f"gen-fake-{uuid.uuid4()}",
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 400, "completion_tokens": 160, "cost": 0.00044 if paid else 0},
    }
