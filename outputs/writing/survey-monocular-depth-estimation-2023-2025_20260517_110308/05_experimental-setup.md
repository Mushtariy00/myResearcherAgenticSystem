# Experimental Setup

## Objective
Detail dataset preparation (weather augmentation for DrivingDepth, splits), hardware and software stack (Docker Ubuntu 22.04, CUDA 12.1, ONNX Runtime/TensorRT, mixed precision, gradient checkpointing), training hyper‑parameters, benchmark protocol (100 runs, latency & throughput measurement), and evaluation metrics as listed.

## Draft
Draft this section by focusing on: Detail dataset preparation (weather augmentation for DrivingDepth, splits), hardware and software stack (Docker Ubuntu 22.04, CUDA 12.1, ONNX Runtime/TensorRT, mixed precision, gradient checkpointing), training hyper‑parameters, benchmark protocol (100 runs, latency & throughput measurement), and evaluation metrics as listed.. Use approved stage outputs and keep claims grounded in evidence.

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
