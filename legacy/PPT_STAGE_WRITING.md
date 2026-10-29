# PPT Stage Guide — Writing
> Agentic Research System
> Status: Partially implemented (outline + draft stubs)

---

## 1. Slide summary (1–2 bullets)
- Produces a section-wise writing plan from experiment context.
- Generates structured markdown stubs for each section.

---

## 2. Purpose
Translate experiment and research outputs into a publication-ready writing plan with explicit review focus.

---

## 3. Inputs
- **ExperimentStageOutput** (goal, config, metrics)
- **Optional experiment summary** (if available)

---

## 4. Outputs
- **WritingStageOutput** (sections, output format, review focus)
- **Per-section markdown files** (`outputs/writing/*/*.md`)
- **Stage manifest** (`outputs/artifacts/*/writing.json`)

---

## 5. Detailed flow (stage logic)
1. LLM generates JSON for:
   - sections with objectives
   - output format
   - review focus
2. Writer storage builds:
   - `00_summary.md`
   - section markdown files with objectives and prompts
3. **Approval gate** at stage completion.

---

## 6. Tools and modules (for PPT citation)
- `orchestration/research_pipeline.py` (`run_writing_stage`)
- `storage/writing_storage.py`
- `schemas/models.py` (`WritingStageOutput`)

---

## 7. Current limitations (honest slide)
- Produces outlines and draft prompts, not full prose sections.
- Evidence linking to literature or experiments is not automated yet.

---

## 8. Planned enhancements
- Generate full drafts with citations tied to evidence snippets.
- Support per-section human feedback loops.
- Export consolidated paper markdown or PDF.

---

## 9. Demo snippets
```bash
run_flow "Survey monocular depth estimation 2023-2025"
```
- Show: `outputs/writing/*/00_summary.md` and section files.

