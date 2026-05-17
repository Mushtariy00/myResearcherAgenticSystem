# Experiments

## Objective
Describe experimental protocol: training for 2 epochs, evaluation metrics (RMSE, AbsRel, inference latency), and tracking of auxiliary metrics (GPU memory, throughput). Present ablation studies for each loss component and scalability analysis.

## Draft
Draft this section by focusing on: Describe experimental protocol: training for 2 epochs, evaluation metrics (RMSE, AbsRel, inference latency), and tracking of auxiliary metrics (GPU memory, throughput). Present ablation studies for each loss component and scalability analysis.. Use approved stage outputs and keep claims grounded in evidence.

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
