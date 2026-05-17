# Results

## Objective
Report quantitative outcomes meeting the targets (RMSE < 0.5, latency < 30 ms) and qualitative depth visualizations. Discuss the impact of each loss term and synthetic data quality on performance.

## Draft
Draft this section by focusing on: Report quantitative outcomes meeting the targets (RMSE < 0.5, latency < 30 ms) and qualitative depth visualizations. Discuss the impact of each loss term and synthetic data quality on performance.. Use approved stage outputs and keep claims grounded in evidence.

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
