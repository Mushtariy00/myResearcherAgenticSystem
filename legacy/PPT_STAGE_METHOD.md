# PPT Stage Guide — Method
> Agentic Research System
> Status: Implemented (memory recall stubbed)

---

## 1. Slide summary (1–2 bullets)
- Turns literature synthesis into concrete research gaps and method proposals.
- Produces a single recommended option with rationale.

---

## 2. Purpose
Extract actionable research directions from the literature stage and lock a method proposal for downstream stages.

---

## 3. Inputs
- **Literature synthesis JSON** (from Stage A)
- **Optional memory context** (planned; currently stubbed)

---

## 4. Outputs
- **Method stage JSON** with research gaps + proposals + recommendation.
- **Stored artifact** (`outputs/method/*.json`)
- **Stage manifest** (`outputs/artifacts/*/method.json`)

---

## 5. Detailed flow (stage logic)
1. Build a structured prompt with the literature synthesis.
2. LLM generates JSON with:
   - `research_gaps`
   - `proposals` (name, rationale, expected benefit, risk)
   - `recommended_option`
3. Robust JSON parsing + validation via Pydantic.
4. Store method artifact + manifest.
5. **Approval gate**: user approves or halts.

---

## 6. Tools and modules (for PPT citation)
- `orchestration/research_pipeline.py` (`run_method_stage`)
- `schemas/models.py` (`MethodStageOutput`)
- `storage/method_storage.py`
- `orchestration/flow_utils.py` (retry + JSON parsing + approval)

---

## 7. Checkpoints and recovery
- **Approval gate** at stage completion.
- LLM retry wrapper and JSON fallback parsing (json/json5/literal).

---

## 8. Risks / limitations (honest slide)
- Outputs can vary across models or prompts.
- Memory recall is not yet wired to a persistent memory backend.

---

## 9. Planned enhancements
- Wire agentmemory MCP for recall + save of method decisions.
- Add explicit guardrails for proposal completeness (architecture, loss, metrics).

---

## 10. Demo snippets
```bash
run_flow "Survey monocular depth estimation 2023-2025"
```
- Show: `outputs/method/*.json`, `outputs/artifacts/*/method.json`

