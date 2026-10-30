"""GROBID 0.9 full-text parsing: the HTTP client and a TEI parser.

GROBID runs inside the lab network (compose profile ``parse``), so its client is an ordinary
httpx client: the SSRF-guarded ``SafeClient`` would refuse its private address.
"""

import re
from typing import Final
from xml.etree.ElementTree import Element, ParseError

import httpx
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring
from pydantic import BaseModel, ConfigDict, Field

from agentic_scholarly.http import RetryPolicy, request
from agentic_scholarly.ids import normalize_arxiv_id, normalize_doi

_TEI: Final = "{http://www.tei-c.org/ns/1.0}"
_YEAR: Final = re.compile(r"(\d{4})")
# Full-text parsing of a long paper on the CRF image takes tens of seconds to minutes.
DEFAULT_TIMEOUT_SECONDS: Final = 300.0
# GROBID answers 503 when all its threads are busy and asks clients to come back in 5-10 s;
# other errors (a 500 on a broken PDF) are not worth repeating.
GROBID_RETRY: Final = RetryPolicy(tries=4, backoff_seconds=5.0, statuses=frozenset({503}))
# Consolidation would make GROBID call Crossref for every paper; metadata comes from our sources.
_FULLTEXT_FORM: Final = {
    "consolidateHeader": "0",
    "consolidateCitations": "0",
    "consolidateFunders": "0",
    "includeRawCitations": "0",
}


class GrobidError(Exception):
    """GROBID could not parse the PDF: ``grobid.unavailable`` (down or busy), ``grobid.failed``
    (an error answer), ``grobid.no_content`` (nothing extracted) or ``grobid.bad_tei``."""

    def __init__(self, code: str, detail: str = "", *, status: int | None = None) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.status = status


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    text: str


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None


class TeiHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    venue: str | None = None
    abstract: str | None = None


class TeiDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header: TeiHeader
    sections: list[Section]
    references: list[Reference]


class GrobidClient:
    """POSTs PDFs to a GROBID service, one document per request."""

    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        retry: RetryPolicy = GROBID_RETRY,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._timeout = httpx.Timeout(timeout_seconds, connect=5.0)
        self._retry = retry

    async def is_alive(self) -> bool:
        """Whether the service finished initialising (``/api/isalive`` answers ``true``)."""
        try:
            response = await self._client.get(
                f"{self._base_url}/api/isalive", timeout=httpx.Timeout(5.0)
            )
        except httpx.RequestError:
            return False
        return response.status_code == 200 and response.text.strip().lower() == "true"

    async def fulltext(self, pdf: bytes) -> TeiDocument:
        """Header, sections and references of a PDF (``processFulltextDocument``)."""
        try:
            response = await request(
                self._client,
                "POST",
                f"{self._base_url}/api/processFulltextDocument",
                data=_FULLTEXT_FORM,
                files={"input": ("paper.pdf", pdf, "application/pdf")},
                timeout=self._timeout,
                retry=self._retry,
            )
        except httpx.RequestError as exc:
            raise GrobidError("grobid.unavailable", type(exc).__name__) from exc
        if response.status_code == 204:
            raise GrobidError("grobid.no_content", "GROBID extracted nothing", status=204)
        if response.status_code == 503:
            raise GrobidError("grobid.unavailable", "all GROBID threads are busy", status=503)
        if response.status_code != 200:
            raise GrobidError(
                "grobid.failed", f"HTTP {response.status_code}", status=response.status_code
            )
        return parse_tei(response.content)


def parse_tei(xml: bytes) -> TeiDocument:
    """Header metadata, body and annex sections, and references from GROBID TEI XML."""
    try:
        root = fromstring(xml, forbid_dtd=True)
    except (ParseError, DefusedXmlException) as exc:
        raise GrobidError("grobid.bad_tei", str(exc)) from exc
    if root.tag != f"{_TEI}TEI":
        raise GrobidError("grobid.bad_tei", f"unexpected root element {root.tag}")
    text = root.find(f"{_TEI}text")
    back = text.find(f"{_TEI}back") if text is not None else None
    return TeiDocument(
        header=_header(root.find(f"{_TEI}teiHeader")),
        sections=_sections(text),
        references=_references(back),
    )


def _header(header: Element | None) -> TeiHeader:
    if header is None:
        return TeiHeader()
    # An empty stand-in keeps the lookups below free of None checks.
    bibl = _found(header.find(f"{_TEI}fileDesc/{_TEI}sourceDesc/{_TEI}biblStruct"))
    title = _first_text(
        header.find(f"{_TEI}fileDesc/{_TEI}titleStmt/{_TEI}title[@type='main']"),
        header.find(f"{_TEI}fileDesc/{_TEI}titleStmt/{_TEI}title"),
        bibl.find(f"{_TEI}analytic/{_TEI}title"),
    )
    published = header.find(f"{_TEI}fileDesc/{_TEI}publicationStmt/{_TEI}date")
    abstract = header.find(f"{_TEI}profileDesc/{_TEI}abstract")
    return TeiHeader(
        title=title,
        authors=_authors(bibl, f"{_TEI}analytic/{_TEI}author"),
        year=_year(published) or _bibl_year(bibl),
        doi=normalize_doi(_idno(bibl, "DOI")),
        arxiv_id=normalize_arxiv_id(_idno(bibl, "arXiv")),
        venue=_first_text(*bibl.findall(f"{_TEI}monogr/{_TEI}title")),
        abstract=_paragraphs(abstract) if abstract is not None else None,
    )


def _sections(text: Element | None) -> list[Section]:
    if text is None:
        return []
    divs = text.findall(f"{_TEI}body/{_TEI}div")
    # Appendices are paper content; acknowledgements, funding and references are not.
    for annex in text.findall(f"{_TEI}back/{_TEI}div[@type='annex']"):
        nested = annex.findall(f"{_TEI}div")
        divs.extend(nested or [annex])
    sections: list[Section] = []
    for div in divs:
        body = _paragraphs(div)
        if body:
            sections.append(Section(title=_first_text(div.find(f"{_TEI}head")), text=body))
    return sections


def _references(back: Element | None) -> list[Reference]:
    if back is None:
        return []
    references: list[Reference] = []
    for bibl in back.iter(f"{_TEI}biblStruct"):
        analytic = _found(bibl.find(f"{_TEI}analytic"))
        title = _first_text(
            analytic.find(f"{_TEI}title[@type='main']"),
            analytic.find(f"{_TEI}title"),
            bibl.find(f"{_TEI}monogr/{_TEI}title"),
        )
        authors = _authors(bibl, f"{_TEI}analytic/{_TEI}author") or _authors(
            bibl, f"{_TEI}monogr/{_TEI}author"
        )
        doi = normalize_doi(_idno(bibl, "DOI"))
        if title or authors or doi:
            references.append(
                Reference(title=title, authors=authors, year=_bibl_year(bibl), doi=doi)
            )
    return references


def _found(element: Element | None) -> Element:
    return element if element is not None else Element(f"{_TEI}empty")


def _text(element: Element | None) -> str | None:
    if element is None:
        return None
    return " ".join("".join(element.itertext()).split()) or None


def _first_text(*elements: Element | None) -> str | None:
    for element in elements:
        text = _text(element)
        if text:
            return text
    return None


def _paragraphs(element: Element) -> str | None:
    """Paragraph text below element (directly or in nested divs), one paragraph per block."""
    paragraphs = [_text(p) for p in element.iter(f"{_TEI}p")]
    return "\n\n".join(p for p in paragraphs if p) or None


def _authors(bibl: Element, path: str) -> list[str]:
    names: list[str] = []
    for author in bibl.findall(path):
        person = author.find(f"{_TEI}persName")
        if person is None:
            continue
        parts = [
            _text(part) for part in person if part.tag in (f"{_TEI}forename", f"{_TEI}surname")
        ]
        name = " ".join(part for part in parts if part)
        if name:
            names.append(name)
    return names


def _idno(bibl: Element, kind: str) -> str | None:
    for idno in bibl.iter(f"{_TEI}idno"):
        if (idno.get("type") or "").lower() == kind.lower():
            return _text(idno)
    return None


def _year(date: Element | None) -> int | None:
    if date is None:
        return None
    match = _YEAR.search(date.get("when") or _text(date) or "")
    year = int(match.group(1)) if match else None
    return year if year is not None and 1000 <= year <= 2100 else None


def _bibl_year(bibl: Element) -> int | None:
    dates = bibl.findall(f"{_TEI}monogr/{_TEI}imprint/{_TEI}date")
    preferred = [date for date in dates if date.get("type") == "published"] or dates
    return next((year for date in preferred if (year := _year(date))), None)
