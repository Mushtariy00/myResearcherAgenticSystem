# Experimental Setup

## Objective
Describe datasets (NYU Depth V2, KITTI, SceneFlow synthetic edge), preprocessing, evaluation resolution (720p), and metrics tracked (abs_rel, RMSE, δ<1.25, FLOPs, memory, FPS, token count, edge RMSE, model size). Provide reproducibility details (docker image, random seeds, hardware specs).

## Draft
Draft this section by focusing on: Describe datasets (NYU Depth V2, KITTI, SceneFlow synthetic edge), preprocessing, evaluation resolution (720p), and metrics tracked (abs_rel, RMSE, δ<1.25, FLOPs, memory, FPS, token count, edge RMSE, model size). Provide reproducibility details (docker image, random seeds, hardware specs).. Use approved stage outputs and keep claims grounded in evidence.

## Review Focus
Ensure the survey context (2023‑2025) is woven throughout, the experimental rigor (metrics, reproducibility) is explicit, and the efficiency‑accuracy trade‑offs are highlighted for edge deployment. Emphasize novelty of hierarchical token pruning and its quantitative impact on real‑time monocular depth estimation.

## Metrics to Reference
- Absolute Relative Error (abs_rel)
- Root Mean Square Error (RMSE)
- Delta Accuracy (δ<1.25)
- FLOPs (GMac)
- Peak GPU Memory (GB)
- Inference FPS
- Token Count per Layer
- Training Loss (L1+SSIM)
- Edge RMSE on Synthetic Set
- Model Size (MB)
