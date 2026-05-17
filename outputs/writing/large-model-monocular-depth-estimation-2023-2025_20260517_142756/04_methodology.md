# Methodology

## Objective
Detail the model architecture (ViT‑B/16 encoder + depth decoder), synthetic dataset creation (10 k samples, rule‑based captions, depth noise), and the three‑component loss (contrastive, masked depth L1, consistency MSE) with weighting scheme. Include training hyper‑parameters, optimizer settings, and hardware/software stack.

## Draft
Draft this section by focusing on: Detail the model architecture (ViT‑B/16 encoder + depth decoder), synthetic dataset creation (10 k samples, rule‑based captions, depth noise), and the three‑component loss (contrastive, masked depth L1, consistency MSE) with weighting scheme. Include training hyper‑parameters, optimizer settings, and hardware/software stack.. Use approved stage outputs and keep claims grounded in evidence.

## Review Focus
Assess clarity of the pipeline description, reproducibility of the synthetic data and training setup, adequacy of the loss combination justification, and whether the reported metrics convincingly demonstrate the claimed RMSE and latency targets.

## Metrics to Reference
- contrastive_loss
- masked_depth_l1_loss
- consistency_mse_loss
- total_training_loss
- validation_RMSE
- validation_AbsRel
- average_inference_latency_ms
- gpu_memory_utilization_percent
- training_throughput_images_per_sec
