# Ablation Studies

## Objective
Isolate effects of (i) token_ratio_schedule, (ii) mixed‑precision vs full‑precision, (iii) gradient checkpointing, and (iv) different loss term weightings. Report statistical significance and early‑stop behavior.

## Draft
Draft this section by focusing on: Isolate effects of (i) token_ratio_schedule, (ii) mixed‑precision vs full‑precision, (iii) gradient checkpointing, and (iv) different loss term weightings. Report statistical significance and early‑stop behavior.. Use approved stage outputs and keep claims grounded in evidence.

## Review Focus
Assess completeness of the trade‑off analysis, relevance of the selected datasets and metrics, rigor of the benchmarking methodology on Snapdragon 8 Gen 2, and clarity of the contribution relative to existing monocular depth surveys (2023‑2025).

## Metrics to Reference
- validation_loss
- validation_abs_rel
- validation_sq_rel
- validation_rmse
- validation_rmse_log
- inference_latency_ms
- throughput_fps
- model_flops
- token_count_before
- token_count_after
- fallback_branch_usage_rate
