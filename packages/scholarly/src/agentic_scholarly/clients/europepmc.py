"""Europe PMC: the PDF of a PMC article, by PMCID.

Europe PMC renders the PDF of an open-access article at a stable article URL, so the candidate
needs no API call; the fetcher finds out whether the article has one. The older backend
(``ptpmcrender.fcgi``) was decommissioned in 2026 and now answers 403; the article URL
redirects to whatever serves the PDF today.
"""

from typing import Final

from agentic_scholarly.ids import normalize_pmcid
from agentic_scholarly.models import OaCandidate

ARTICLES_URL: Final = "https://europepmc.org/articles"


def pdf_candidate(pmcid: str) -> OaCandidate:
    normalized = normalize_pmcid(pmcid)
    if normalized is None:
        raise ValueError(f"not a PMCID: {pmcid!r}")
    return OaCandidate(url=f"{ARTICLES_URL}/{normalized}?pdf=render", source="europepmc")
