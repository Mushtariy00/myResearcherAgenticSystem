# Abstract

## Objective
Summarize the motivation (real‑time monocular depth on edge GPUs), the novelty (systematic evaluation of token sparsification ratios on LCT‑Depth), key experimental settings (Snapdragon 8 Gen 2, weather‑augmented KITTI/NYU/DrivingDepth), and headline results (trade‑off curves, latency ≤30 ms with ≤5 % RMSE loss).

## Draft
Draft this section by focusing on: Summarize the motivation (real‑time monocular depth on edge GPUs), the novelty (systematic evaluation of token sparsification ratios on LCT‑Depth), key experimental settings (Snapdragon 8 Gen 2, weather‑augmented KITTI/NYU/DrivingDepth), and headline results (trade‑off curves, latency ≤30 ms with ≤5 % RMSE loss).. Use approved stage outputs and keep claims grounded in evidence.

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
