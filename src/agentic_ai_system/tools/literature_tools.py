from __future__ import annotations

import json
import re
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
        tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())
        stop_words = {
            # "survey",
            # "benchmark",
            # "recent",
            # "advances",
            # "advance",
            # "overview",
            # "review",
            # "analysis",
            "test1",
            "test2"
        }
        keywords = []
        for token in tokens:
            if token.isdigit():
                # Drop standalone years and ranges like 2023-2025
                continue
            if len(token) <= 2 or token in stop_words:
                continue
            keywords.append(token)
        if not keywords:
            keywords = [tok for tok in tokens if len(tok) > 2][:3]  # Fallback: keep first 3 meaningful tokens

        def _fetch_arxiv(query_str: str) -> tuple[bytes | None, str | None]:
            encoded_query = urllib.parse.quote(query_str)
            url = (
                "https://export.arxiv.org/api/query"
                f"?search_query={encoded_query}&start=0&max_results={max_results}"
                "&sortBy=relevance&sortOrder=descending"
            )
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "agentic_ai_system/0.1 literature-search"},
            )
            raw_xml = b""
            last_error: str | None = None
            for attempt in range(1, 4):
                try:
                    with urllib.request.urlopen(request, timeout=30) as response:
                        raw_xml = response.read()
                    return raw_xml or None, None
                except socket.timeout as exc:
                    last_error = "Socket timeout"
                    if attempt < 3:
                        time.sleep(attempt * 2)  # Exponential backoff
                        continue
                    return None, last_error
                except urllib.error.HTTPError as exc:
                    last_error = f"HTTP {exc.code}"
                    if exc.code == 429 and attempt < 3:
                        time.sleep(attempt * 2)
                        continue
                    return None, last_error
                except urllib.error.URLError as exc:
                    last_error = f"Network error: {exc.reason}"
                    if attempt < 3:
                        time.sleep(attempt * 2)
                        continue
                    return None, last_error
            return raw_xml or None, last_error

        def _parse_entries(raw_xml: bytes) -> list[dict[str, str]]:
            root = ET.fromstring(raw_xml)
            namespace = {"atom": "http://www.w3.org/2005/Atom"}
            papers: list[dict[str, str]] = []
            for entry in root.findall("atom:entry", namespace):
                entry_id = (entry.findtext("atom:id", default="", namespaces=namespace) or "").strip()
                title = (entry.findtext("atom:title", default="", namespaces=namespace) or "").strip()
                summary = (entry.findtext("atom:summary", default="", namespaces=namespace) or "").strip()
                published = (entry.findtext("atom:published", default="", namespaces=namespace) or "").strip()
                authors = [
                    (author.findtext("atom:name", default="", namespaces=namespace) or "").strip()
                    for author in entry.findall("atom:author", namespace)
                ]
                link = ""
                for child in entry.findall("atom:link", namespace):
                    rel = child.attrib.get("rel", "")
                    href = child.attrib.get("href", "")
                    if rel == "alternate" and href:
                        link = href
                        break
                if not link:
                    link = entry_id
                papers.append(
                    {
                        "id": entry_id,
                        "title": title,
                        "summary": summary,
                        "url": link,
                        "published": published,
                        "authors": [author for author in authors if author],
                        "source": "arXiv",
                    }
                )
            return papers

        # Primary query: AND across core terms
        primary_query = " AND ".join([f"all:{kw}" for kw in keywords])
        raw_xml, error = _fetch_arxiv(primary_query)
        if not raw_xml:
            return json.dumps(
                {
                    "query": query,
                    "source": "arXiv",
                    "error": error or "No response payload",
                    "papers": [],
                },
                ensure_ascii=True,
            )
        papers = _parse_entries(raw_xml)

        # Fallback: relax query if no results (use OR across core terms)
        if not papers and len(keywords) >= 2:
            fallback_query = " OR ".join([f"all:{kw}" for kw in keywords[:3]])
            raw_xml, error = _fetch_arxiv(fallback_query)
            if raw_xml:
                papers = _parse_entries(raw_xml)

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
