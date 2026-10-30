"""PMC Cloud Service: the PDF of a PMC article on AWS Open Data, by PMCID.

The PMC FTP service and OA web service were retired in August 2026; article files now live in
the public ``pmc-oa-opendata`` bucket as ``PMC<n>.<version>/PMC<n>.<version>.pdf``. Most
articles only have version 1, and not every version has a PDF, so this candidate is a good
guess that the fetcher confirms or rejects (S3 answers 403/404 for a missing object).
"""

from typing import Final

from agentic_scholarly.ids import normalize_pmcid
from agentic_scholarly.models import OaCandidate

BUCKET_URL: Final = "https://pmc-oa-opendata.s3.amazonaws.com"


def pdf_candidate(pmcid: str, version: int = 1) -> OaCandidate:
    normalized = normalize_pmcid(pmcid)
    if normalized is None:
        raise ValueError(f"not a PMCID: {pmcid!r}")
    if version < 1:
        raise ValueError("PMC article versions start at 1")
    key = f"{normalized}.{version}"
    return OaCandidate(url=f"{BUCKET_URL}/{key}/{key}.pdf", source="pmc")
