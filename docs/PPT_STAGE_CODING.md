# PPT Stage Guide — Coding
> Agentic Research System
> Status: Universal scaffold is wired; coding agent is restricted to task-specific modules only

---

## 1. Slide summary (1–2 bullets)
- **Scaffold-and-wire** phase: builds a runnable pipeline, not a final model.
- Enforced by **hard gates** and **diff-only** changes.

---

## 2. Purpose
Turn the approved Method proposal into a **verified, runnable pipeline scaffold** that downstream Experiment stage can execute safely.

---

## 3. Hard prerequisite gates (must pass before coding)
1. **Method proposal locked** (human-approved, includes architecture name, loss, metrics, and novel components flagged).
2. **Environment manifest verified** (`env_manifest.json` with Python, CUDA, key packages).
3. **Data contract signed** (`data_contract.json` with dataset schema, splits, labels, and approval).

If any gate fails → emit `BlockingCheckpoint` in Flow state and halt.

---

## 4. Layer 0 — Scaffold (Agent-owned)
**Goal:** A runnable end-to-end pipeline skeleton with **synthetic-only data**.  
**Deliverable:** Diff against repo, no full file overwrites.

**Structure (example):**
```
config/     (smoke.yaml, base.yaml)
data/       (loader.py, transforms.py)
model/      (base.py, registry.py)
train/      (loop.py, metrics.py, evaluate.py)
outputs/    (experiments/)
env_manifest.json
data_contract.json
```

**Smoke test contract:**
```bash
python train/loop.py --config config/smoke.yaml --dry-run
```
Must finish < 30s and exit 0.

---

## 5. Layer 1 — Data Integration (Human-led, Agent-assisted)
**Ownership boundary:**
- Human: dataset access, preprocessing logic, label schema.
- Agent: DataLoader wiring, synthetic fallback, shape/dtype validation.

**Deliverable:** `data_report.json` with split counts, shape/dtype, parity check.
Failure → `SyntheticParityFailed` and halt.

---

## 6. Layer 2 — Baseline Model (Human-approved, Agent-wired)
1. **Zero baseline** first (sanity check for pipeline plumbing).
2. **Target architecture wiring** via config-driven registry.
3. Novel/custom components → `HumanAuthorshipRequired` event, halt until provided.

**Checkpoint:** human review of forward pass (shape/dtype/grad flow).

---

## 7. Layer 3 — Training Loop Hardening (Agent-owned)
Features:
- Determinism + seed logging
- NaN/Inf checks + optional gradient clipping
- Checkpointing (`best.pt`, `last.pt`)
- Structured logs (`metrics.jsonl`)
- Optional MLflow adapter (if env confirms)
- `--dry-run` flag

**Deliverable:** `run_config.json` with env/data hashes.

---

## 8. Layer 4 — Evaluation Harness (Shared)
- Human defines domain metrics; agent wires harness.
- Outputs: `eval_report.json` + `eval_summary.md`.

---

## 9. Handoff to Experiment Stage
**Deliverable:** `pipeline_manifest.json`
```json
{
  "entry_point": "python train/loop.py --config <path>",
  "dry_run_entry": "python train/loop.py --config config/smoke.yaml --dry-run",
  "expected_inputs": ["config YAML path"],
  "expected_outputs": ["outputs/experiments/<run_id>/"],
  "config_schema": "config/base.yaml",
  "dry_run_max_seconds": 60,
  "env_manifest": "env_manifest.json",
  "data_contract": "data_contract.json",
  "stage_approved_by": "human",
  "stage_approved_at": "<timestamp>"
}
```

**Handoff checklist (all required):**
1. Gates passed and recorded.
2. Scaffold diff reviewed.
3. Smoke test passes (<30s).
4. Data report approved.
5. Forward pass validated.
6. Dry-run passes (<60s).
7. Pipeline manifest written.

---

## 10. Flow events (for PPT)
- `BlockingCheckpoint` — gate failed.
- `HumanAuthorshipRequired` — novel component flagged.
- `SmokeTestFailed` — dry-run failed.
- `SyntheticParityFailed` — real vs synthetic mismatch.
- `HandoffReady` — pipeline manifest approved.

---

## 11. Current implementation gap (honest slide)
- Diff-only enforcement and layered gating details are not yet implemented.
- Data integration layer (data_report.json + parity checks) is still a gap.

---

## 12. Key files (for citation)
- `coding_stage_plan.md` (source of truth)
- `execution/sandbox_executor.py`
- `orchestration/research_pipeline.py`
