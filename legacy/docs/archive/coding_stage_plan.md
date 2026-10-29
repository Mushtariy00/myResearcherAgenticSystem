# Coding Stage — Strategic Plan
> Part of the CrewAI Agentic Research System  
> Status: Planning | Last updated: May 2026

---

## 1. Core Philosophy

The coding stage is a **scaffold-and-wire** phase, not a build-from-zero phase.

The agent is a **careful plumber, not an architect.** It connects, wires, and scaffolds approved components. It does not invent ML logic, choose architectures, or make research decisions. Every layer must be independently testable. Every change is delivered as a diff, never a full overwrite.

**Three non-negotiable principles:**
- If a prerequisite gate fails → emit a structured `BlockingCheckpoint` in Flow state and halt. No partial work.
- Every layer runs standalone with synthetic data before real data is introduced.
- The environment manifest (`env_manifest.json`) is the single source of truth for all downstream artifacts.

---

## 2. Position in the Flow

```
Method Agent (approved proposal)
        │
        ▼
[GATE: Method approved?] ──✗──▶ HALT
        │ ✓
        ▼
Coding Stage (this document)
        │
        ▼
Experiment Agent (receives pipeline_manifest.json)
```

The coding stage **receives** a locked, human-approved method proposal.  
It **delivers** a verified, runnable pipeline — not a trained model.

---

## 3. Hard Prerequisite Gates (all must pass before work begins)

These are not steps. They are blocking conditions. The Flow does not advance until all three are confirmed and written to Flow state.

### Gate 1 — Method Proposal Locked
- A human-approved method spec from the Method agent exists in Flow state
- Spec includes: target architecture name, loss function, evaluation metric(s), and any novel components flagged for human authorship
- **No spec → No start**

### Gate 2 — Environment Manifest Verified
The agent audits the environment and writes `env_manifest.json`:

```json
{
  "python_version": "3.11.x",
  "cuda_version": "12.x or null",
  "gpu_available": true,
  "key_packages": { "torch": "2.x", "numpy": "1.x", "...": "..." },
  "platform": "linux/mac/win",
  "verified_at": "<timestamp>"
}
```

- Smoke test: imports key packages, checks GPU visibility, confirms no version conflicts
- **Manifest missing or smoke test fails → HALT**

### Gate 3 — Data Contract Signed
Before any model code is written, the dataset is confirmed and documented:

```json
{
  "dataset_name": "...",
  "source": "local_path | download_script | synthetic_only",
  "input_shape": [batch, channels, height, width],
  "input_dtype": "float32",
  "label_schema": "...",
  "splits": { "train": 0.8, "val": 0.1, "test": 0.1 },
  "sample_count": { "train": 0, "val": 0, "test": 0 },
  "approved_by": "human",
  "approved_at": "<timestamp>"
}
```

- Human provides: dataset access, preprocessing logic definition, label schema
- Agent provides: validation script, shape/dtype checks, synthetic fallback generator
- **Data contract missing → HALT**

---

## 4. Layer 0 — Scaffold (Agent-owned)

**Goal:** A runnable end-to-end pipeline skeleton with no real ML logic.  
**Owner:** Agent  
**Deliverable:** Diff against existing repo. No fresh writes if files already exist.

### Repository Structure

```
config/
  smoke.yaml           ← minimal config for smoke test (tiny data, 1 epoch)
  base.yaml            ← full config template with all fields documented
data/
  loader.py            ← DataLoader stub returning synthetic tensors
  transforms.py        ← identity transforms as named placeholders
model/
  base.py              ← abstract model interface (forward signature only)
  registry.py          ← maps config string → model class
train/
  loop.py              ← training loop calling stubs end-to-end
  metrics.py           ← loss logging only, no domain metrics yet
  evaluate.py          ← evaluation stub
outputs/
  experiments/         ← run directories land here
env_manifest.json      ← written by Gate 2
data_contract.json     ← written by Gate 3
```

### Smoke Test Contract

```bash
python train/loop.py --config config/smoke.yaml --dry-run
```

- Must complete in **< 30 seconds**
- Must produce a valid (empty) output directory under `outputs/experiments/`
- Must exit with code `0`
- Uses synthetic data only — no real dataset required

**Checkpoint:** Human reviews scaffold diff and smoke test output before Layer 1 begins.

---

## 5. Layer 1 — Data Integration (Human-led, Agent-assisted)

**Goal:** Replace synthetic stubs with real data pipeline.  
**Owner:** Human for logic; Agent for mechanical wiring.

### Ownership Boundary

| Task | Owner |
|---|---|
| Dataset access (credentials, paths, downloads) | **Human** |
| Preprocessing transform logic (normalization, augmentation, tokenization) | **Human** |
| Domain-specific label handling | **Human** |
| DataLoader wrapper implementation | Agent (after schema confirmed) |
| Synthetic fallback generator | Agent |
| Batch shape/dtype validation | Agent |
| `data_report.json` generation | Agent |

### Agent Deliverables

`data_report.json` — written after real data is provided:
```json
{
  "split_counts": { "train": 0, "val": 0, "test": 0 },
  "input_shape": "...",
  "input_dtype": "...",
  "label_distribution": {},
  "null_count": 0,
  "synthetic_parity_check": "pass | fail"
}
```

**Synthetic parity check:** real batches and synthetic batches must produce identical shapes and dtypes. If they don't, the agent flags the mismatch and halts.

**Checkpoint:** Human reviews `data_report.json` and approves before any model code is written.

---

## 6. Layer 2 — Baseline Model (Human-approved architecture, Agent-wired)

**Goal:** Wire the Method-approved architecture into the scaffold and validate the pipeline plumbing.  
**Owner:** Architecture design → Human (via Method agent approval). Wiring → Agent.

### Step 1 — Zero baseline first
Before the target architecture, the agent wires the simplest possible model:
- A single linear layer, or random weights, or a pass-through
- Purpose: prove the pipeline plumbing is correct before adding complexity
- Must produce a valid forward pass (correct output shape, no NaN/Inf)

### Step 2 — Target architecture integration
- Agent implements the Method-approved model behind `registry.py`
- Architecture choice, depth, and width are config-driven — never hardcoded
- Switching architectures requires only a config change, no code change

### Ownership Boundary for Architecture

| Component | Owner |
|---|---|
| Architecture selection | **Human** (via approved Method proposal) |
| Novel components (custom attention, custom loss) | **Human** |
| Wiring approved architecture into registry | Agent |
| Forward pass validation | Agent |
| Config-driven parameterization | Agent |

**If the Method proposal flags any component as novel or custom:**  
→ Agent emits a `HumanAuthorshipRequired` event in Flow state  
→ Halts until human provides the implementation  
→ Agent then wires it in

**Checkpoint:** Human reviews forward pass output (shape, dtype, gradient flow check) before any training loop runs.

---

## 7. Layer 3 — Training Loop Hardening (Agent-owned, Human review)

**Goal:** Harden the scaffold loop into a reliable, reproducible training loop.  
**Owner:** Agent authors; Human reviews and approves before real training runs.

### Features the Agent Implements

| Feature | Detail |
|---|---|
| Reproducibility | Fixed seeds, deterministic ops, logged in `run_config.json` |
| Safety checks | NaN/Inf detection per batch, gradient clipping hook (disabled by default) |
| Checkpointing | Saves `best.pt` and `last.pt` on configurable cadence |
| Structured logging | `metrics.jsonl` — loss + primary metric per epoch |
| MLflow adapter | Optional; wired in if MLflow is confirmed available in env manifest |
| Dry-run flag | `--dry-run`: runs 2 batches of 1 epoch, then exits cleanly |
| Early stopping | Implemented but disabled by default; enabled via config |

### `run_config.json` (written at start of every run)

```json
{
  "run_id": "uuid",
  "timestamp": "...",
  "config_path": "...",
  "env_manifest_hash": "...",
  "data_contract_hash": "...",
  "model": "...",
  "seed": 42,
  "dry_run": false
}
```

The `env_manifest_hash` and `data_contract_hash` tie every run to its exact environment and data state. If either changes, runs are considered invalidated.

**Checkpoint:** Human reviews loop diff and a dry-run output (`--dry-run`) before any real training is authorized.

---

## 8. Layer 4 — Evaluation Harness (Shared)

**Goal:** Reproducible evaluation pipeline that can be called by the Experiment agent.  
**Owner:** Agent for harness; Human for domain metric definitions.

### Ownership Boundary

| Task | Owner |
|---|---|
| Domain metric definitions (F1, BLEU, IoU, perplexity, etc.) | **Human** |
| Metric wiring into harness | Agent (after human defines) |
| Checkpoint loading and inference loop | Agent |
| `eval_report.json` generation | Agent |
| `eval_summary.md` generation | Agent |

### `eval_report.json`

```json
{
  "run_id": "...",
  "checkpoint": "best.pt",
  "split": "test",
  "metrics": {},
  "sample_outputs": [],
  "evaluated_at": "..."
}
```

### `eval_summary.md`

Human-readable summary generated from `eval_report.json`. Consumed by the Writing agent downstream.

---

## 9. Handoff to Experiment Agent

The coding stage's final deliverable is a **verified, runnable pipeline** — not a trained model.

### `pipeline_manifest.json`

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

### Handoff Checklist

- [ ] All gates passed and recorded in Flow state
- [ ] Scaffold diff reviewed and committed
- [ ] Smoke test passes (`< 30s`, exit `0`)
- [ ] Data report approved by human
- [ ] Forward pass validated (shape, dtype, gradients)
- [ ] Dry-run passes (`< 60s`, exit `0`)
- [ ] `pipeline_manifest.json` written
- [ ] Human approval recorded in Flow state

Only after all checklist items are confirmed does the Experiment agent receive the manifest.

---

## 10. Ownership Summary

| Component | Owner |
|---|---|
| Scaffold structure | Agent |
| Environment manifest | Agent (human validates) |
| Data access and credentials | **Human** |
| Preprocessing and transform logic | **Human** |
| DataLoader wrapper | Agent (after schema confirmed) |
| Synthetic data fallback | Agent |
| Architecture selection | **Human** (via Method agent) |
| Novel architecture components | **Human** |
| Architecture wiring | Agent |
| Training loop plumbing | Agent |
| Hyperparameter values | **Human** (via config approval) |
| Domain metric definitions | **Human** |
| Evaluation harness wiring | Agent |
| All diffs and scaffolding | Agent |

---

## 11. What the Agent Never Does

- Does not choose or invent ML architectures
- Does not define preprocessing transforms
- Does not select hyperparameters
- Does not author novel components (custom attention, custom loss functions)
- Does not access external datasets or APIs without an approved data contract
- Does not overwrite existing files — diffs only
- Does not proceed past a failed gate — halts with a structured error

---

## 12. Flow State Events

| Event | Trigger | Effect |
|---|---|---|
| `BlockingCheckpoint` | Any gate fails | Flow halts; surfaces to human |
| `HumanAuthorshipRequired` | Novel component flagged in Method proposal | Flow pauses; waits for human implementation |
| `CheckpointApproved` | Human approves a layer review | Flow advances to next layer |
| `SmokeTestFailed` | Smoke test exits non-zero or exceeds time limit | Flow halts; agent surfaces error details |
| `SyntheticParityFailed` | Real/synthetic batch shapes don't match | Flow halts; agent surfaces mismatch details |
| `HandoffReady` | All checklist items confirmed | Experiment agent receives `pipeline_manifest.json` |

---

## 13. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Environment mismatch between dev and training machines | `env_manifest.json` locked at Gate 2; all runs reference it |
| Dataset unavailable or access fails | Synthetic fallback always available; pipeline never blocks on real data |
| Method proposal is ambiguous or underspecified | Gate 1 requires explicit architecture name and flagged novel components; ambiguity → HALT |
| Novel component flagged but human delays authorship | `HumanAuthorshipRequired` event surfaces in Flow; coding stage is blocked, not broken |
| Agent produces large rewrites instead of diffs | Enforced by policy: agent must produce patch-style diffs; full file rewrites trigger a review warning |
| Real training run consumes expensive GPU time on a broken pipeline | Dry-run gate is mandatory before Experiment agent receives the manifest |

---

*This document is the single source of truth for the Coding Stage design.  
For sprint execution, see the main CrewAI Dev Plan (crewai_dev_plan.md).*
