# Phase 2 design: the real literature stage

Status: draft (2026-10-30). This replaces the demo literature search (`literature.demo_search`)
with real search, open-access PDFs, parsing and paper analysis. The output contract does not
change (`agentic_core.schemas.LiteratureOutput`), so the web app needs no change.

## Goal and exit criteria (from docs/PLAN.md, Phase 2)

- A literature stage on a real topic finds papers in OpenAlex, Semantic Scholar and arXiv
  (Crossref for metadata), screens them, fetches open-access PDFs, parses them and analyses the
  included papers with evidence quotes that point at real pages.
- It works on a paid budget and on free models only; on free models it fits the free quota
  (about 30 LLM calls for 20 papers).
- Papers are stored once in the lab's library and found again by full-text search.
- SSRF tests pass: `169.254.169.254`, `localhost`, private ranges and redirect chains to them
  are refused.
- No silent placeholders: a paper without a PDF is analysed from its abstract and says so; a
  failed step fails or flags the output `degraded`, never invents content.

## Flow

```text
plan (LLM) → search (per query × source) → merge & de-duplicate → rank → screen (LLM, batched)
→ fetch PDFs (open-access waterfall) → parse (GROBID, else page text, else abstract)
→ analyse each included paper (LLM, paper text as delimited data) → synthesise (LLM)
→ LiteratureOutput
```

The stage is a child workflow, `LiteratureWorkflow`, one per stage attempt. RunWorkflow starts
it under a new `workflow.patched` marker instead of `execute_stage` for the literature stage;
older runs keep the current path. The child orchestrates small activities on two task queues:

| Activity | Queue (role) | Does |
|---|---|---|
| `lit_plan` | `arp-main` (agents) | research plan (exists today inside execute_stage) |
| `lit_search` | `arp-fetch` (fetch) | one source × all queries; writes candidates to `run_papers` |
| `lit_screen` | `arp-main` | LLM screening, 10 papers per call; decision, relevance, reason |
| `lit_fetch_pdf` | `arp-fetch` | one paper: waterfall → validated PDF → content-addressed file |
| `lit_parse_pdf` | `arp-fetch` | one paper: GROBID → sections; fallback page text |
| `lit_analyze` | `arp-main` | one paper: PaperAnalysis with verified evidence quotes |
| `lit_synthesize` | `arp-main` | key findings and synthesis from the analyses |
| `lit_store_output` | `arp-main` | builds and validates LiteratureOutput, stores the StageOutput |

- Payloads carry ids only; intermediate results live in the database (`papers`, `paper_texts`,
  `run_papers`), so a retried activity resumes instead of starting over.
- The fetch role has internet egress and no gateway token; the agents role reaches only the
  gateway. In dev both run in one worker process unless `ARP_WORKER_ROLES` splits them.
- Fetch and parse run per paper with bounded concurrency (4); analyses run 4 at a time. Each
  activity heartbeats; cancel reaches all of them (`WAIT_CANCELLATION_COMPLETED`).
- Gateway waits (429, paused budget) use the same workflow helper as RunWorkflow, so a rate
  limit pauses one activity, not the run.
- Progress goes to the run's event log as `log` events with message codes and counts
  (`literature.searched`, `literature.screened`, `literature.fetched`, `literature.analyzed`).

## Sources (`packages/scholarly`, a new uv workspace member, no DB access)

| Source | Use | Limit (lab-wide, Valkey token bucket) |
|---|---|---|
| OpenAlex | search with `publication_year` filter; OA locations; abstracts (inverted index) | 10 req/s without a key, 30 with `ARP_OPENALEX_API_KEY` (`api_key` param) |
| Semantic Scholar | search; `openAccessPdf`, `externalIds` | 1 req/s (`x-api-key` header when `ARP_S2_API_KEY` is set) |
| arXiv | search (Atom API at export.arxiv.org); PDFs | 1 request / 3 s, one connection at a time |
| Crossref | DOI metadata, retraction notices (`update-to`) | 10 req/s, `mailto` in the User-Agent |
| Unpaywall | DOI → best open-access PDF | email parameter (`ARP_CONTACT_EMAIL`) |
| Europe PMC | PMCID → PDF | polite use |
| CORE | title → repository PDF (only with `ARP_CORE_API_KEY`) | per key |

- Every client: async httpx, 20 s timeout, retries on 429/5xx with backoff and Retry-After, a
  User-Agent naming the lab and contact email, mocked-HTTP tests (respx).
- `PaperMeta` is the normalised record: ids (doi lowercased, arxiv id without version, s2,
  openalex, pmcid), title, authors, year, venue, abstract, citation count, OA PDF candidates
  with their source, retracted flag.
- De-duplication key, in order: DOI → arXiv id → S2 id → normalised title + year (±1) + first
  author's surname.
- Ranking before screening: source rank (best position across queries), citations per year,
  recency, title/abstract match with the plan's queries. The top `3 × max_papers` go to
  screening.

## Open-access waterfall and the SSRF guard

Candidates in order, stopping at the first valid PDF: arXiv (`arxiv.org/pdf/{id}`) → Europe
PMC / PMC (PMCID) → Unpaywall `best_oa_location.url_for_pdf` → OpenAlex
`best_oa_location.pdf_url` → Semantic Scholar `openAccessPdf.url` → CORE `downloadUrl`. No
Sci-Hub, Google Scholar, ResearchGate or publisher scraping.

The fetcher (`scholarly.fetch`) is the only code that downloads from URLs found in metadata:

- `https` only; the host is resolved once and every address must be public: no loopback,
  private, link-local (169.254/16, fe80::/10), CGNAT, multicast, reserved, unique-local or
  IPv4-mapped forms of those. The connection goes to the vetted address (no second lookup).
- Redirects are followed by hand, at most 5, each target vetted the same way.
- Streamed with a 40 MB cap and a total deadline; `Content-Type` must be a PDF or octet
  stream and the body must start with `%PDF-` and be at least 10 KB.
- Files are stored content-addressed: `ARP_DATA_DIR/papers/<sha256[:2]>/<sha256>.pdf`. A paper
  that already has a file is never downloaded again.
- arXiv PDFs are stored for research use and shown only to signed-in lab members, never served
  publicly (arXiv terms of use).

## Parsing

- GROBID 0.9.1, CRF image (`grobid/grobid:0.9.1-crf`), compose profile `parse`, started on
  demand, memory limit 4 GB, one document at a time. `processFulltextDocument` → TEI XML,
  parsed with defusedxml into sections (title, text), references and header metadata.
- Page text from pypdfium2 for every PDF: evidence quotes are verified against it and the
  viewer highlights them.
- When GROBID is down or fails, sections fall back to page text; when there is no PDF, the
  paper is analysed from its abstract (`PaperRef.pdf_available = false`).
- `paper_texts.tsv` (title, abstract, section text; `english` configuration, GIN index) powers
  the library's full-text search. Docling (tables, formulas) is a later addition.

## LLM steps (through the gateway; prompts versioned in the worker)

| Role | Output | Calls for 20 papers | Max output tokens |
|---|---|---|---|
| `literature.plan` | ResearchPlan | 1 | 1,500 |
| `literature.screen` | decisions for 10 papers | 6 | 2,000 |
| `literature.analyze` | PaperAnalysis | ≤ 20 | 1,500 |
| `literature.synthesize` | key findings + synthesis | 1 | 2,500 |

- Agents that read papers have no tools; the paper text goes in a delimited block marked as
  data, trimmed to a token budget (sections in order: abstract, introduction, method, results,
  conclusion).
- Strict schemas with one repair retry (as the plan step does today).
- Evidence quotes are kept only when they match the page text of the cited page (normalised
  whitespace and hyphenation); an analysis whose quotes all fail keeps its text but no quotes.

## Data model (migration after 7c3e9a51d2b4)

- `papers`: uuid id; unique nullable `doi`, `arxiv_id`, `s2_id`, `openalex_id`; `pmcid`;
  title; authors (JSONB); year; venue; abstract; citation_count; `pdf_sha256`; `pdf_status`
  (`unknown | available | abstract_only | failed`); `pdf_source`; `retracted`; timestamps.
- `paper_texts`: paper_id (PK, FK); parser (`grobid-0.9.1 | pdfium | abstract`); sections
  (JSONB); references (JSONB); page_count; pages (JSONB, text per page); `tsv` with a GIN index.
- `run_papers`: (stage_run_id, paper_id) PK; run_id; query; source; rank; relevance;
  decision; decision_reason; analysed.
- The stage output keeps a snapshot of `PaperRef`s for review; `paper_id` is `papers.id`.

## API (contract unchanged)

- `GET /papers?q=`, `GET /papers/{id}`: from `papers` + `run_papers` (+ `paper_texts.tsv` for
  `q`), `demo: false`. Demo outputs from seeded runs stay visible in their runs.
- `GET /papers/{id}/file`: streams the stored PDF to project members (`nosniff`, inline for the
  viewer, `attachment` for downloads); 404 when the paper has no file.

## Later in Phase 2

- Real method and writing stages; citation verification (each `[n]` must resolve to an
  included paper of the run).
- Email notifications (SMTP; Mailpit in dev) and approval reminders.
- Caddy TLS on the server, off-box backups and a restore drill.
