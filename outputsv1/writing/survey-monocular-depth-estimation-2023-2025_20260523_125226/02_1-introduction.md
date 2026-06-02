# 1. Introduction

## Objective
Motivate monocular depth estimation, outline practical deployment constraints (GPU memory < 4 GB, latency < 30 ms @1080p), and introduce the need for a systematic survey that bridges recent transformer‑based approaches with hardware‑aware evaluation.

## Draft
Draft this section by focusing on: Motivate monocular depth estimation, outline practical deployment constraints (GPU memory < 4 GB, latency < 30 ms @1080p), and introduce the need for a systematic survey that bridges recent transformer‑based approaches with hardware‑aware evaluation.. Use approved stage outputs and keep claims grounded in evidence.

## Review Focus
Accuracy vs. efficiency trade‑offs, memory and latency compliance, gradient preservation in adaptive binning, reproducibility of experimental setup, and completeness of the 2023‑2025 literature coverage.

## Metrics to Reference
- per_batch_training_time_ms
- per_frame_inference_latency_ms
- gpu_memory_usage_gb
- training_l1_loss
- adaptive_binning_gradient_norm
- validation_l1_loss
