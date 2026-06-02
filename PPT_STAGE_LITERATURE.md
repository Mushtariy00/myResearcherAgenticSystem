# PPT Stage Guide — Literature
> Agentic Research System
> Status: Implemented (open-access fetch only)

---

## 1. Slide summary (1–2 bullets)
- Multi-pass literature pipeline: search → screen → fetch → analyze → synthesize.
- Produces traceable artifacts for each sub-step.

---

## 2. Purpose
Convert a topic into a credible, evidence-grounded literature synthesis with transparent intermediate artifacts.

---

## 3. Inputs
- **Topic string** (e.g., “Monocular depth estimation 2023–2025”)

---

## 4. Outputs
- **Literature synthesis JSON** (`outputs/literature/*.json`)
- **Screening output** (`outputs/literature_screen/*`)
- **Full-text fetch manifest + text files** (`outputs/literature_fetch/*`)
- **Per-paper analysis outputs** (`outputs/literature_analysis/*`)
- **Stage manifest** (`outputs/artifacts/*/literature.json`)

---

## 5. Detailed flow (stage logic)
1. **Query expansion** → build a small set of topical queries.
2. **Search** → run ArXiv + Semantic Scholar tools, collect candidates.
3. **Deduplicate + rank** → score by topical relevance and citations.
4. **Screening pass (LLM)** → select top candidates with rationale.
5. **Full-text fetch** → resolve open-access PDF URLs and extract text.
6. **Paper analysis (LLM)** → extract findings, limitations, evidence.
7. **Synthesis (LLM)** → produce a compact literature synthesis.
8. **Persist artifacts + manifests** → each sub-stage is stored separately.
9. **Approval gate** → user approves or halts the flow.

---

## 6. Tools and modules (for PPT citation)
- `tools/literature_tools.py` — `ArxivSearchTool`, `SemanticScholarSearchTool`
- `tools/paper_fetch_tools.py` — `PaperFullTextFetchTool` (open-access PDF resolver + text extraction)
- `orchestration/literature_pipeline.py`
- `storage/*` — screen/fetch/analysis/output persistence

---

## 7. Checkpoints and recovery
- **Approval gate** at the end of the stage.
- **Fallback synthesis** if LLM fails or JSON is malformed.
- **Rate-limit handling** (Semantic Scholar skipped after 429).

---

## 8. Risks / limitations (honest slide)
- Paywalled papers are not fetchable via current open-access resolver.
- Retrieval quality depends on external APIs and network reliability.
- Topic matching is permissive (current filter accepts most results).

---

## 9. Planned enhancements
- Integrate waterfall PDF retrieval (Unpaywall/OpenAlex/CORE/PMC).
- Add citation graph expansion after screening.
- Add relevance scoring benchmarks and retrieval metrics.

---

## 10. Demo snippets
```bash
run_flow "Survey monocular depth estimation 2023-2025"
```
- Show: `outputs/literature/`, `outputs/literature_fetch/`, `outputs/literature_analysis/`

