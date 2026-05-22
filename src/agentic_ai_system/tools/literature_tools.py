from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class LiteratureSearchInput(BaseModel):
    query: str = Field(..., description="Search query for literature discovery.")
    max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of papers to return.",
    )


class ArxivSearchTool(BaseTool):
    name: str = "arxiv_search"
    description: str = "Searches arXiv and returns structured paper metadata."
    args_schema: Type[BaseModel] = LiteratureSearchInput

    def _run(self, query: str, max_results: int = 5) -> str:
        # Use keyword search instead of exact phrase matching
        # ArXiv works better with AND of individual terms: "monocular AND depth AND estimation"
        keywords = query.split()
        # Filter out short words like "2023-2025", "and", etc., keep only meaningful terms
        keywords = [kw for kw in keywords if len(kw) > 2 and not kw.isdigit()]
        if not keywords:
            keywords = query.split()[:3]  # Fallback: use first 3 words
        
        # Build query: connect keywords with AND for better results
        search_query = " AND ".join(keywords)
        encoded_query = urllib.parse.quote(search_query)
        url = (
            "http://export.arxiv.org/api/query"
            f"?search_query=all:{encoded_query}&start=0&max_results={max_results}"
            "&sortBy=relevance&sortOrder=descending"
        )
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "agentic_ai_system/0.1 literature-search"},
        )
        raw_xml = b""
        for attempt in range(1, 4):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    raw_xml = response.read()
                break
            except socket.timeout as exc:
                if attempt < 3:
                    time.sleep(attempt * 2)  # Exponential backoff
                    continue
                return json.dumps(
                    {
                        "query": query,
                        "source": "arXiv",
                        "error": f"Socket timeout after {attempt} attempts",
                        "papers": [],
                    },
                    ensure_ascii=True,
                )
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < 3:
                    time.sleep(attempt * 2)
                    continue
                return json.dumps(
                    {
                        "query": query,
                        "source": "arXiv",
                        "error": f"HTTP {exc.code}",
                        "papers": [],
                    },
                    ensure_ascii=True,
                )
            except urllib.error.URLError as exc:
                if attempt < 3:
                    time.sleep(attempt * 2)
                    continue
                return json.dumps(
                    {
                        "query": query,
                        "source": "arXiv",
                        "error": f"Network error: {exc.reason}",
                        "papers": [],
                    },
                    ensure_ascii=True,
                )
        if not raw_xml:
            return json.dumps(
                {
                    "query": query,
                    "source": "arXiv",
                    "error": "No response payload",
                    "papers": [],
                },
                ensure_ascii=True,
            )

        root = ET.fromstring(raw_xml)
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        papers: list[dict[str, str]] = []
        for entry in root.findall("atom:entry", namespace):
            title = (entry.findtext("atom:title", default="", namespaces=namespace) or "").strip()
            summary = (entry.findtext("atom:summary", default="", namespaces=namespace) or "").strip()
            link = ""
            for child in entry.findall("atom:link", namespace):
                rel = child.attrib.get("rel", "")
                href = child.attrib.get("href", "")
                if rel == "alternate" and href:
                    link = href
                    break
            if not link:
                link = (entry.findtext("atom:id", default="", namespaces=namespace) or "").strip()
            papers.append(
                {
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "source": "arXiv",
                }
            )

        return json.dumps({"query": query, "source": "arXiv", "papers": papers}, ensure_ascii=True)


class SemanticScholarSearchTool(BaseTool):
    name: str = "semantic_scholar_search"
    description: str = "Searches Semantic Scholar and returns structured paper metadata."
    args_schema: Type[BaseModel] = LiteratureSearchInput

    def _run(self, query: str, max_results: int = 5) -> str:
        encoded_query = urllib.parse.quote(query)
        fields = urllib.parse.quote("title,year,citationCount,url,abstract")
        url = (
            "https://api.semanticscholar.org/graph/v1/paper/search"
            f"?query={encoded_query}&limit={max_results}&fields={fields}"
        )
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "agentic_ai_system/0.1 literature-search"},
        )
        payload = {}
        for attempt in range(1, 4):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except socket.timeout as exc:
                if attempt < 3:
                    time.sleep(attempt * 2)  # Exponential backoff
                    continue
                return json.dumps(
                    {
                        "query": query,
                        "source": "Semantic Scholar",
                        "error": f"Socket timeout after {attempt} attempts",
                        "papers": [],
                    },
                    ensure_ascii=True,
                )
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < 3:
                    time.sleep(attempt * 2)
                    continue
                return json.dumps(
                    {
                        "query": query,
                        "source": "Semantic Scholar",
                        "error": f"HTTP {exc.code}",
                        "papers": [],
                    },
                    ensure_ascii=True,
                )
            except urllib.error.URLError as exc:
                if attempt < 3:
                    time.sleep(attempt * 2)
                    continue
                return json.dumps(
                    {
                        "query": query,
                        "source": "Semantic Scholar",
                        "error": f"Network error: {exc.reason}",
                        "papers": [],
                    },
                    ensure_ascii=True,
                )
        if not payload:
            return json.dumps(
                {
                    "query": query,
                    "source": "Semantic Scholar",
                    "error": "No response payload",
                    "papers": [],
                },
                ensure_ascii=True,
            )

        papers = []
        for entry in payload.get("data", []):
            papers.append(
                {
                    "title": entry.get("title", ""),
                    "summary": entry.get("abstract", ""),
                    "url": entry.get("url", ""),
                    "year": str(entry.get("year", "")),
                    "citation_count": str(entry.get("citationCount", "")),
                    "source": "Semantic Scholar",
                }
            )

        return json.dumps(
            {"query": query, "source": "Semantic Scholar", "papers": papers},
            ensure_ascii=True,
        )
