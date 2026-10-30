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

### First version: one activity whose steps are cached in the database

The stage stays one `execute_stage` activity. The literature runner works through the steps
above, and every step's result lands in the database as it is produced:
- the candidates, their ranks and screening decisions in `run_papers`;
- PDFs and their parsed text at the paper level (`papers`, `paper_texts`);
- each analysis in `run_papers.analysis`.

Every LLM call has a semantic idempotency key: `<stage_run_id>:screen:<batch>`,
`<stage_run_id>:analyze:<paper key>`, `<stage_run_id>:synthesize`, plus `:call-N` per retry
inside a step. An attempt that runs again therefore resumes rather than starting over:
- after a gateway wait (429), a pause for the lab balance or a worker crash, finished steps
  are read back from the database;
- paid answers are replayed from the gateway journal for free.

Because it stays one activity, the workflow is unchanged. The waits and pauses RunWorkflow
handles (STAGE_WAITS_PATCH) and cancel (`WAIT_CANCELLATION_COMPLETED`) apply as they are:
- The activity heartbeats throughout.
- PDF fetch and parse run per paper with bounded concurrency (4), and analyses run 3 at a
  time.
- The literature stage gets a 2-hour `start_to_close_timeout`. Changing an activity option
  doesn't change the workflow's command sequence.

Progress goes to the run's event log as `log` events with message codes and counts:
`literature.searched`, `literature.screened`, `literature.fetched`, `literature.analyzed` and
`literature.synthesized`. A source that fails or runs out of quota is logged, and the stage
continues with the others.

### Later: trust zones (Phase 4 hardening)

Fetching moves to its own worker process and task queue (`arp-fetch`). That process has
internet egress and no gateway token; the agents process reaches only the gateway. It needs a
child workflow per stage attempt that orchestrates activities on both queues. Until then, the
SSRF guard in `agentic_scholarly.fetch` is the protection: every resolved address must be
public, and the socket connects to the address that was vetted.

## Sources (`packages/scholarly`, a uv workspace member, no DB access)

The live check on 2026-10-30 found these limits:
- **OpenAlex without a key:** a budget of $0.10 a day at $0.001 per search, about 100
  searches for the whole lab. A free key raises the budget to $1 a day.
- **Semantic Scholar without a key:** answers 429. It needs `ARP_S2_API_KEY`; until then the
  stage logs that the source is unavailable and goes on without it.
- **Europe PMC:** refuses this network with 403, so the PMC cloud bucket comes first.

| Source | Use | Limit (lab-wide, Valkey token bucket) |
|---|---|---|
| OpenAlex | search with `publication_year` filter; OA locations; abstracts (inverted index) | 10 req/s without a key, 30 with `ARP_OPENALEX_API_KEY` (sent as a Bearer header, never in the URL) |
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

## Data model (migration 8d4f2b6a1c37)

- `papers`:
  - `key`: unique, the paper's id in stage outputs and URLs. It is the first external id the
    paper was found under: `doi:<doi>`, `arxiv:<id>`, `s2:<id>` or `openalex:<W id>`. It never
    changes.
  - unique nullable `doi` (lowercase), `arxiv_id` (no version), `s2_id`, `openalex_id`;
    `pmcid`. A paper found again under another id merges into its row.
  - title, authors (JSONB), year, venue, abstract, citation_count, url, `retracted`, `demo`
    (seeded).
  - `pdf_status` (`unknown | available | abstract_only | failed`), `pdf_sha256`, `pdf_source`,
    `pdf_url`, `pdf_checked_at`.
  - `search`: a generated tsvector over title and abstract, with a GIN index.
- `paper_texts`:
  - paper_id (PK, FK); parser (`grobid-0.9.1 | pdfium`); page_count;
  - pages (JSONB, the text of each page); sections (JSONB `[{title, text}]`); references
    (JSONB);
  - `tsv`: generated from the sections, with a GIN index.
- `run_papers`:
  - (stage_run_id, paper_id) PK; run_id;
  - hits (JSONB `[{source, query, position}]`); rank; score;
  - relevance, decision and decision_reason from screening;
  - analysis (PaperAnalysis JSON) and analysis_model.
- The stage output keeps a snapshot of `PaperRef`s for review. `PaperRef.paper_id` is
  `papers.key`.

## Settings (worker and API, repo-root `.env`)

- `ARP_DATA_DIR`: where files live. PDFs go under `papers/`. The default is
  `~/.local/share/arp`, outside the repo, because the Next dev server watches the repo.
- `ARP_CONTACT_EMAIL`: the contact in the scholarly APIs' User-Agent, and the email Unpaywall
  requires. Without it Unpaywall is skipped.
- `ARP_OPENALEX_API_KEY`, `ARP_S2_API_KEY`, `ARP_CORE_API_KEY`: optional; a source without
  its key runs at its keyless limits or is skipped.
- `ARP_GROBID_URL` (default `http://127.0.0.1:8070`). Start GROBID with
  `docker compose --profile parse up -d grobid`. When it is down, sections fall back to page
  text.

## API (contract unchanged)

- `GET /papers?q=` and `GET /papers/{id}` read `papers` and `run_papers`; for `q` they use
  `papers.search` and `paper_texts.tsv`. A paper is visible to members of a project with a
  run that found it, and to lab admins. `demo` comes from `papers.demo`; the seed writes its
  demo papers into these tables too.
- `GET /papers/{id}/file` streams the stored PDF to those same users as an attachment with
  `nosniff`; the viewer fetches it itself. A seeded demo paper without a stored file still
  gets the generated preview PDF. Any other paper without a file gets 404.

## Later in Phase 2

- Real method and writing stages; citation verification (each `[n]` must resolve to an
  included paper of the run).
- Email notifications (SMTP; Mailpit in dev) and approval reminders.
- Caddy TLS on the server, off-box backups and a restore drill.
