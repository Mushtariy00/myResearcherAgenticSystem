from __future__ import annotations

from pydantic import BaseModel, Field


class PaperFetchResult(BaseModel):
    index: int = 0
    title: str = ""
    source: str = ""
    source_url: str = ""
    resolved_pdf_url: str = ""
    page_count: int = 0
    text_length: int = 0
    text_chunks: list[str] = Field(default_factory=list)
    text_path: str = ""
    status: str = ""
    error: str = ""


class LiteratureFetchOutput(BaseModel):
    papers: list[PaperFetchResult] = Field(default_factory=list)


class PaperAnalysisOutput(BaseModel):
    index: int = 0
    title: str = ""
    source: str = ""
    relevance_assessment: str = ""
    key_findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_snippets: list[str] = Field(default_factory=list)
    summary: str = ""
