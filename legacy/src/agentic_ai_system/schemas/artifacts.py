from __future__ import annotations

from pydantic import BaseModel, Field


class StageArtifactManifest(BaseModel):
    contract_version: str = "1"
    stage: str = ""
    topic: str = ""
    generated_at: str = ""
    primary_path: str = ""
    auxiliary_paths: list[str] = Field(default_factory=list)
    summary: str = ""
    status: str = "completed"
    metadata: dict[str, object] = Field(default_factory=dict)
