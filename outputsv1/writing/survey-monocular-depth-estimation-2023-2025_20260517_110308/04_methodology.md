# Methodology

## Objective
Describe the LCT‑Depth architecture, token sparsification mechanism, token_ratio_schedule, loss functions (scale‑invariant log‑RMSE, edge‑aware gradient), optimizer settings, and the fallback branch design. Include a diagram of the training/inference pipeline on Snapdragon 8 Gen 2.

## Draft
Draft this section by focusing on: Describe the LCT‑Depth architecture, token sparsification mechanism, token_ratio_schedule, loss functions (scale‑invariant log‑RMSE, edge‑aware gradient), optimizer settings, and the fallback branch design. Include a diagram of the training/inference pipeline on Snapdragon 8 Gen 2.. Use approved stage outputs and keep claims grounded in evidence.

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
