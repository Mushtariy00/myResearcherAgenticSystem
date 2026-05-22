from __future__ import annotations

import json
import re
import time
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


def _fetch_url_with_retry(url: str, max_retries: int = 3, timeout: int = 30) -> bytes | None:
    """Fetch URL bytes with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "agentic_ai_system/0.1 pdf-fetcher"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                if "pdf" not in content_type.lower():
                    return None
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            else:
                return None
        except Exception:
            return None
    return None


def _get_unpaywall_pdf_url(doi: str) -> str | None:
    """
    Query Unpaywall API (unpaywall.org/api/v2/) to find OA PDF URL.
    Docs: https://unpaywall.org/products/api
    """
    if not doi:
        return None
    
    doi_clean = doi.strip().lower()
    if not doi_clean.startswith("http"):
        if not doi_clean.startswith("10."):
            return None
        url = f"https://api.unpaywall.org/v2/{doi_clean}?email=system@example.com"
    else:
        url = doi
    
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "agentic_ai_system/0.1 unpaywall-adapter"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        
        if data.get("is_oa"):
            oa_location = data.get("best_oa_location") or data.get("oa_locations", [{}])[0]
            if oa_location and oa_location.get("url_for_pdf"):
                return oa_location["url_for_pdf"]
            elif oa_location and oa_location.get("url"):
                return oa_location["url"]
        return None
    except Exception:
        return None


def _get_openalex_pdf_url(doi: str | None = None, title: str | None = None) -> str | None:
    """
    Query OpenAlex API (openalex.org) to find OA PDF URL or DOI.
    Docs: https://docs.openalex.org
    """
    if not doi and not title:
        return None
    
    if doi:
        doi_clean = doi.strip().lower()
        if not doi_clean.startswith("http"):
            if doi_clean.startswith("10."):
                query = f'doi:"{doi_clean}"'
            else:
                return None
        else:
            return None
    else:
        query = f'title:"{title}"' if title else None
    
    if not query:
        return None
    
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://api.openalex.org/works?filter={encoded_query}&per-page=1"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "agentic_ai_system/0.1 openalex-adapter"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        
        if data.get("results"):
            work = data["results"][0]
            if work.get("open_access", {}).get("oa_url"):
                return work["open_access"]["oa_url"]
            if work.get("open_access", {}).get("is_oa"):
                best_oa = work.get("open_access", {}).get("oa_location")
                if best_oa and best_oa.get("url_for_pdf"):
                    return best_oa["url_for_pdf"]
        return None
    except Exception:
        return None


def resolve_pdf_url_waterfall(
    source_url: str,
    doi: str | None = None,
    title: str | None = None,
) -> str | None:
    """
    Waterfall PDF URL resolution strategy:
    1. Try arXiv direct (if source is arXiv)
    2. Try Unpaywall API (if DOI available)
    3. Try OpenAlex API (if DOI or title available)
    4. Try HTML meta tag parsing (any URL)
    Returns the first successful PDF URL or None.
    """
    # Step 1: arXiv direct
    arxiv_url = _resolve_arxiv_pdf_url(source_url)
    if arxiv_url:
        return arxiv_url
    
    # Step 2: Unpaywall (DOI required)
    if doi:
        unpaywall_url = _get_unpaywall_pdf_url(doi)
        if unpaywall_url:
            return unpaywall_url
    
    # Step 3: OpenAlex (DOI or title)
    if doi or title:
        openalex_url = _get_openalex_pdf_url(doi=doi, title=title)
        if openalex_url:
            return openalex_url
    
    # Step 4: HTML meta tag parsing
    html_url = _resolve_html_pdf_url(source_url)
    if html_url:
        return html_url
    
    return None


def fetch_pdf_with_waterfall(
    source_url: str,
    doi: str | None = None,
    title: str | None = None,
    max_pages: int | None = None,
) -> dict[str, object]:
    """
    Fetch PDF using waterfall strategy. Returns structured result.
    Tries: arXiv → Unpaywall → OpenAlex → HTML parsing.
    """
    resolved_url = resolve_pdf_url_waterfall(source_url, doi=doi, title=title)
    
    if not resolved_url:
        return {
            "source_url": source_url,
            "doi": doi or "",
            "title": title or "",
            "resolved_pdf_url": "",
            "status": "unresolved",
            "strategy": "none",
            "page_count": 0,
            "text_length": 0,
            "text": "",
            "error": "No PDF URL found via waterfall (arXiv/Unpaywall/OpenAlex/HTML)",
        }
    
    # Determine strategy used
    strategy = "unknown"
    if _resolve_arxiv_pdf_url(source_url) == resolved_url:
        strategy = "arxiv"
    elif doi and _get_unpaywall_pdf_url(doi) == resolved_url:
        strategy = "unpaywall"
    elif _get_openalex_pdf_url(doi=doi, title=title) == resolved_url:
        strategy = "openalex"
    elif _resolve_html_pdf_url(source_url) == resolved_url:
        strategy = "html"
    
    # Fetch PDF bytes
    pdf_bytes = _fetch_url_with_retry(resolved_url, max_retries=3, timeout=45)
    if not pdf_bytes:
        return {
            "source_url": source_url,
            "doi": doi or "",
            "title": title or "",
            "resolved_pdf_url": resolved_url,
            "status": "fetch_failed",
            "strategy": strategy,
            "page_count": 0,
            "text_length": 0,
            "text": "",
            "error": "Failed to fetch PDF from resolved URL",
        }
    
    # Extract text
    try:
        text, page_count = extract_pdf_text(pdf_bytes, max_pages=max_pages)
        return {
            "source_url": source_url,
            "doi": doi or "",
            "title": title or "",
            "resolved_pdf_url": resolved_url,
            "status": "ok",
            "strategy": strategy,
            "page_count": page_count,
            "text_length": len(text),
            "text": text,
            "error": "",
        }
    except Exception as e:
        return {
            "source_url": source_url,
            "doi": doi or "",
            "title": title or "",
            "resolved_pdf_url": resolved_url,
            "status": "extract_error",
            "strategy": strategy,
            "page_count": 0,
            "text_length": 0,
            "text": "",
            "error": f"PDF extraction failed: {str(e)}",
        }

