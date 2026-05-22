# PDF access plan for research agent

## Goal

For each relevant paper found during research, attempt to retrieve the full PDF through a waterfall of free, legal, reliable sources. If no PDF is found, fall back to abstract-only analysis — not a failure, still useful.

---

## Tier 1 — Guaranteed free access

No registration. No rate limits. Direct PDF URLs. Use these first.

### arXiv

- **Coverage:** CS, machine learning, physics, math, statistics, biology, economics  
- **How it works:** Every arXiv paper has a stable ID (e.g. `2301.07041`). The PDF URL is always `https://arxiv.org/pdf/{id}`  
- **Detection:** If a paper URL contains `arxiv.org/abs/` or the source field is `arxiv`, extract the ID and build the PDF link directly  
- **Reliability:** 100% — if the paper is on arXiv, the PDF is always available  
- **Rate limit:** None in normal use. Add a 1s delay between requests to be polite

https://arxiv.org/pdf/2301.07041

https://arxiv.org/pdf/2301.07041v2    ← specific version

### PubMed Central (PMC)

- **Coverage:** Biomedical and life science papers with NIH funding mandate  
- **How it works:** Papers with a PMCID have free full text. URL pattern: `https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/`  
- **Detection:** Semantic Scholar and OpenAlex return `pmcid` in their metadata  
- **Reliability:** 100% for papers that have a PMCID

### Europe PMC

- **Coverage:** Superset of PubMed Central — includes additional funders (Wellcome, HHMI, etc.)  
- **API:** `https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf`  
- **Use case:** Try this if PMC fails or paper is not US-funded

---

## Tier 2 — Reliable via API (requires DOI)

These APIs take a DOI and return an open-access PDF URL if one legally exists. Chain them in order — stop at the first successful URL.

### Unpaywall

- **What it does:** Finds legal open-access versions of papers using DOI  
- **API:** `https://api.unpaywall.org/v2/{doi}?email=your@email.com`  
- **Key required:** No account. Just an email address in the query string  
- **Response field:** `best_oa_location.url` → PDF URL, or `null`  
- **Hit rate:** \~50% of all academic papers have a legal OA version  
- **Rate limit:** 100,000 requests/day free

url \= f"https://api.unpaywall.org/v2/{doi}?email=agent@research.com"

response \= requests.get(url).json()

pdf\_url \= response.get("best\_oa\_location", {}).get("url\_for\_pdf")

### OpenAlex

- **What it does:** Open academic graph covering 250M+ works, with OA status per paper  
- **API:** `https://api.openalex.org/works/{doi}`  (no key needed)  
- **Response field:** `open_access.oa_url` → PDF URL, or `null`  
- **Hit rate:** Broader coverage than Unpaywall alone. Best for non-English and non-US papers  
- **Rate limit:** 100,000 requests/day without a key. Add `mailto=` param to get polite pool

doi\_encoded \= doi.replace("/", "%2F")

url \= f"https://api.openalex.org/works/doi:{doi\_encoded}?mailto=agent@research.com"

response \= requests.get(url).json()

pdf\_url \= response.get("open\_access", {}).get("oa\_url")

### Semantic Scholar

- **What it does:** Already used for paper search. Reuse the same API — just add the `openAccessPdf` field  
- **API:** `https://api.semanticscholar.org/graph/v1/paper/{paper_id}?fields=openAccessPdf`  
- **Response field:** `openAccessPdf.url` → PDF URL, or `null`  
- **Hit rate:** Good for CS and ML papers specifically  
- **Note:** Use the Semantic Scholar paper ID (returned during search), not DOI

url \= f"https://api.semanticscholar.org/graph/v1/paper/{paper\_id}?fields=openAccessPdf"

response \= requests.get(url).json()

pdf\_url \= response.get("openAccessPdf", {}) or {}

pdf\_url \= pdf\_url.get("url")

---

## Tier 3 — Good coverage, lightweight setup

Use these to supplement the first two tiers, especially for papers not on arXiv.

### CORE

- **What it does:** Aggregates full-text OA papers from 10,000+ repositories worldwide — 200M+ papers  
- **API:** `https://api.core.ac.uk/v3/search/works?q={title}&api_key={key}`  
- **Key required:** Yes — free, takes 1 minute at [https://core.ac.uk/services/api](https://core.ac.uk/services/api)  
- **Response field:** `results[0].downloadUrl` → PDF URL  
- **Best for:** Papers from institutional repositories that are not on arXiv

headers \= {"Authorization": f"Bearer {CORE\_API\_KEY}"}

url \= f"https://api.core.ac.uk/v3/search/works?q={title\_encoded}\&limit=1"

response \= requests.get(url, headers=headers).json()

pdf\_url \= response.get("results", \[{}\])\[0\].get("downloadUrl")

### bioRxiv / medRxiv

- **What it does:** Life science and medical preprints with direct PDF access  
- **API:** `https://api.biorxiv.org/details/biorxiv/{doi}/na/json`  
- **Key required:** None  
- **Response field:** `collection[0].preprint_url` → append `/full.pdf` for the PDF  
- **Use case:** Life science papers not yet published or without a PMC record

### DOAJ / PLoS

- **What it does:** Fully open-access journals — every paper has a public PDF  
- **PLoS direct PDF:** `https://journals.plos.org/plosone/article/file?id={doi}&type=printable`  
- **DOAJ API:** `https://doaj.org/api/search/articles/{doi}`  
- **Use case:** High-quality papers from fully OA journals

---

## Tier 4 — Do not use

| Source | Reason |
| :---- | :---- |
| **Sci-Hub** | Legally risky in most jurisdictions. Gets blocked by IP. Unreliable programmatically. Not suitable for an automated agent. |
| **Google Scholar** | No official API. Scraping violates ToS. Rate-limited and blocked aggressively. Will break silently. |
| **ResearchGate** | Login required for most PDFs. No API. Scraping violates ToS. |
| **Elsevier / Springer direct** | Paywalled. Attempting downloads triggers CAPTCHA or IP block. |

---

## Recommended waterfall per paper

For each paper, try sources in this order. Stop as soon as a PDF URL is found.

1\. Is it an arXiv paper?

   → Yes: build URL directly from arXiv ID → download

   → No: continue

2\. Does it have a PMCID?

   → Yes: try PMC → try Europe PMC → download

   → No: continue

3\. Does it have a DOI?

   → Query Unpaywall        → if url found → download

   → Query OpenAlex         → if url found → download

   → Query Semantic Scholar → if url found → download

   → continue

4\. Is it a life science preprint?

   → Try bioRxiv / medRxiv API → download

   → continue

5\. Does it have a title searchable in CORE?

   → Query CORE API → if downloadUrl found → download

   → continue

6\. No PDF found anywhere

   → Log as "abstract only"

   → Proceed with abstract analysis (Claude still useful here)

   → Do not block pipeline

---

## Expected outcomes

| Scenario | Expected PDF hit rate |
| :---- | :---- |
| ML / CS papers (arXiv-heavy) | 80–90% |
| Biomedical papers (PMC-covered) | 70–80% |
| General academic mix | 60–75% |
| Papers with no OA version | 0% → abstract fallback |

Papers with no PDF found are not dropped — they continue through the pipeline using abstract-only analysis.

---

## Implementation notes

- **Retry logic:** Each HTTP request should retry once on timeout (5s timeout, 1 retry)  
- **Validation:** After download, check `Content-Type: application/pdf` before saving. Reject HTML responses (login pages, error pages)  
- **Caching:** Store successfully downloaded PDFs by paper ID or DOI hash. Never download the same paper twice  
- **Delay:** 0.5–1s between API calls to avoid triggering rate limits  
- **Headers:** Always set a `User-Agent` string identifying the agent (e.g. `ResearchAgent/1.0`)  
- **File size check:** Reject PDFs smaller than 10KB — likely an error page saved as PDF  
- **Logging:** Log source, success/failure, and reason for every paper. This makes debugging fast

---

## Keys and setup required

| Source | Setup needed |
| :---- | :---- |
| arXiv | None |
| PubMed Central | None |
| Europe PMC | None |
| Unpaywall | Email address in query param (no account) |
| OpenAlex | None (add `mailto=` param for higher rate limit) |
| Semantic Scholar | None for basic use. Optional API key for higher limits |
| CORE | Free API key — register at core.ac.uk/services/api |
| bioRxiv / medRxiv | None |

Total paid services required: **zero.**

---

## What to implement first

1. arXiv direct PDF — covers most ML/CV papers immediately, zero setup  
2. Unpaywall \+ OpenAlex fallback — covers the next largest chunk, no keys  
3. Semantic Scholar OA field — already in the codebase, just add the field  
4. Abstract-only fallback — always available, never blocks the pipeline  
5. CORE \+ PMC — add after the above are stable, as supplementary coverage

