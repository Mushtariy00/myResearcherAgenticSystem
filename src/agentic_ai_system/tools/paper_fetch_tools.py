from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Type

import fitz
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class PaperFetchInput(BaseModel):
    url: str = Field(..., description="Source URL for the paper.")


def _is_file_url(url: str) -> bool:
    return url.startswith("file://") or Path(url).exists()


def _read_file_bytes(url: str) -> bytes:
    path = Path(urllib.parse.urlparse(url).path if url.startswith("file://") else url)
    return path.read_bytes()


def _resolve_arxiv_pdf_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    if "arxiv.org" not in parsed.netloc:
        return None
    if parsed.path.startswith("/pdf/"):
        return url
    match = re.search(r"/abs/([^/?#]+)", parsed.path)
    if not match:
        return None
    paper_id = match.group(1)
    if not paper_id.endswith(".pdf"):
        paper_id = f"{paper_id}.pdf"
    return f"https://arxiv.org/pdf/{paper_id}"


def _resolve_html_pdf_url(url: str) -> str | None:
    request = urllib.request.Request(url, headers={"User-Agent": "agentic_ai_system/0.1 pdf-resolver"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return None

    meta_match = re.search(
        r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    if meta_match:
        return meta_match.group(1)

    href_match = re.search(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', html, flags=re.IGNORECASE)
    if href_match:
        candidate = href_match.group(1)
        return urllib.parse.urljoin(url, candidate)

    return None


def resolve_open_access_pdf_url(url: str) -> str | None:
    if _is_file_url(url):
        return url
    if url.lower().endswith(".pdf"):
        return url
    arxiv_url = _resolve_arxiv_pdf_url(url)
    if arxiv_url:
        return arxiv_url
    return _resolve_html_pdf_url(url)


def extract_pdf_text(pdf_bytes: bytes, max_pages: int | None = None) -> tuple[str, int]:
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_total = document.page_count
    pages = range(page_total) if max_pages is None else range(min(page_total, max_pages))
    texts: list[str] = []
    for page_number in pages:
        texts.append(document.load_page(page_number).get_text("text").strip())
    document.close()
    return "\n\n".join(texts).strip(), page_total


def fetch_open_access_full_text(url: str, max_pages: int | None = None) -> dict[str, object]:
    resolved_url = resolve_open_access_pdf_url(url)
    if not resolved_url:
        return {
            "source_url": url,
            "resolved_pdf_url": "",
            "status": "unresolved",
            "page_count": 0,
            "text": "",
            "error": "Could not resolve an open-access PDF URL.",
        }

    try:
        if _is_file_url(resolved_url):
            pdf_bytes = _read_file_bytes(resolved_url)
        else:
            request = urllib.request.Request(
                resolved_url,
                headers={"User-Agent": "agentic_ai_system/0.1 fulltext-fetch"},
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                pdf_bytes = response.read()
    except urllib.error.HTTPError as exc:
        return {
            "source_url": url,
            "resolved_pdf_url": resolved_url,
            "status": "http_error",
            "page_count": 0,
            "text": "",
            "error": f"HTTP {exc.code}",
        }
    except urllib.error.URLError as exc:
        return {
            "source_url": url,
            "resolved_pdf_url": resolved_url,
            "status": "network_error",
            "page_count": 0,
            "text": "",
            "error": f"Network error: {exc.reason}",
        }
    except Exception as exc:
        return {
            "source_url": url,
            "resolved_pdf_url": resolved_url,
            "status": "fetch_error",
            "page_count": 0,
            "text": "",
            "error": str(exc),
        }

    try:
        text, page_count = extract_pdf_text(pdf_bytes, max_pages=max_pages)
    except Exception as exc:
        return {
            "source_url": url,
            "resolved_pdf_url": resolved_url,
            "status": "extract_error",
            "page_count": 0,
            "text": "",
            "error": str(exc),
        }

    return {
        "source_url": url,
        "resolved_pdf_url": resolved_url,
        "status": "ok",
        "page_count": page_count,
        "text": text,
        "error": "",
    }


class PaperFullTextFetchTool(BaseTool):
    name: str = "paper_full_text_fetch"
    description: str = "Resolves an open-access paper URL and extracts full PDF text."
    args_schema: Type[BaseModel] = PaperFetchInput

    def _run(self, url: str) -> str:
        return json.dumps(fetch_open_access_full_text(url), ensure_ascii=True)
