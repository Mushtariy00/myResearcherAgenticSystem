"""Normalisers for paper identifiers and titles.

Every source spells identifiers its own way (DOI URLs, versioned arXiv ids, PMCIDs without the
prefix, OpenAlex URLs). These functions map each spelling to one canonical form and return None
for anything that is not a valid identifier, so clients can pass raw values straight in.
"""

import re
import unicodedata

_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_DOI = re.compile(r"^10\.\d{4,9}/\S+$")
# DataCite registers a DOI for every arXiv paper: 10.48550/arXiv.<id>.
_ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$", re.IGNORECASE)
_ARXIV_PREFIX = re.compile(
    r"^(?:arxiv:|https?://(?:www\.|export\.)?arxiv\.org/(?:abs|pdf)/)", re.IGNORECASE
)
_ARXIV_NEW = re.compile(r"^(\d{4}\.\d{4,5})(?:v\d+)?$")
# Identifiers before April 2007: archive(.SUBJECT-CLASS)/YYMMNNN, e.g. math.GT/0309136.
_ARXIV_OLD = re.compile(r"^([a-z][a-z-]*(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$")
_OPENALEX = re.compile(r"^(?:https?://openalex\.org/)?W(\d+)$", re.IGNORECASE)
_PMCID = re.compile(r"^(?:PMC)?(\d{1,10})(?:\.\d+)?$", re.IGNORECASE)
_PMC_HOSTS = re.compile(r"^https?://(?:[a-z.]*\.)?(?:ncbi\.nlm\.nih\.gov|europepmc\.org)/")
_S2_ID = re.compile(r"^[0-9a-f]{40}$")


def normalize_doi(value: object) -> str | None:
    """A DOI in lower case without a URL or ``doi:`` prefix, or None if value is not a DOI."""
    if not isinstance(value, str):
        return None
    # A trailing period is sentence punctuation picked up with the DOI, never part of it.
    doi = _DOI_PREFIX.sub("", value.strip()).strip().rstrip(".").lower()
    return doi if _DOI.match(doi) else None


def arxiv_id_from_doi(doi: str | None) -> str | None:
    """The arXiv id inside an arXiv DataCite DOI (10.48550/arxiv.<id>), else None."""
    if not doi:
        return None
    match = _ARXIV_DOI.match(doi.strip())
    return normalize_arxiv_id(match.group(1)) if match else None


def normalize_arxiv_id(value: object) -> str | None:
    """An arXiv id without its version suffix (2301.07041, hep-th/9901001), or None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    from_doi = _ARXIV_DOI.match(text)
    if from_doi:
        text = from_doi.group(1)
    text = _ARXIV_PREFIX.sub("", text)
    # GROBID writes ids as "arXiv:1706.03762v5[cs.CL]"; links may end in ".pdf" or a slash.
    text = re.sub(r"\[[^\]]*\]$", "", text).strip().rstrip("/").removesuffix(".pdf")
    new = _ARXIV_NEW.match(text)
    if new:
        return new.group(1)
    old = _ARXIV_OLD.match(text)
    return old.group(1) if old else None


def normalize_openalex_id(value: object) -> str | None:
    """An OpenAlex work id (W2741809807) from an id or an openalex.org URL, or None."""
    if not isinstance(value, str):
        return None
    match = _OPENALEX.match(value.strip())
    return f"W{match.group(1)}" if match else None


def normalize_pmcid(value: object) -> str | None:
    """A PMCID with its prefix (PMC3531190) from a PMCID, bare digits or a PMC URL, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return f"PMC{value}" if value > 0 else None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if "/" in text:
        # OpenAlex: https://www.ncbi.nlm.nih.gov/pmc/articles/<digits>; PMC pages end in the id.
        if not _PMC_HOSTS.match(text):
            return None
        text = text.rstrip("/").rsplit("/", 1)[1]
    match = _PMCID.match(text)
    if not match or int(match.group(1)) == 0:
        return None
    return f"PMC{int(match.group(1))}"


def normalize_s2_id(value: object) -> str | None:
    """A Semantic Scholar paper id (40 hex characters), or None."""
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    return text if _S2_ID.match(text) else None


def normalize_title(title: str) -> str:
    """A title as lowercase words without accents or punctuation, for matching across sources.

    Letters outside Latin (Greek, CJK, Hangul) are kept, so non-English titles still compare.
    """
    decomposed = unicodedata.normalize("NFKD", title.casefold())
    kept = "".join(
        char if char.isalnum() else " " for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(kept.split())
