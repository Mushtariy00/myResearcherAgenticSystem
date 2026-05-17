# Introduction

## Objective
Introduce monocular depth estimation, challenges on embedded GPUs, related sparsification techniques, and the specific research gap (lack of quantitative trade‑off analysis for token sparsification on modern mobile AI accelerators). State contributions: (1) benchmark suite, (2) token‑ratio schedule study, (3) fallback branch analysis, (4) open‑source reproducible pipeline.

## Draft
Draft this section by focusing on: Introduce monocular depth estimation, challenges on embedded GPUs, related sparsification techniques, and the specific research gap (lack of quantitative trade‑off analysis for token sparsification on modern mobile AI accelerators). State contributions: (1) benchmark suite, (2) token‑ratio schedule study, (3) fallback branch analysis, (4) open‑source reproducible pipeline.. Use approved stage outputs and keep claims grounded in evidence.

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
