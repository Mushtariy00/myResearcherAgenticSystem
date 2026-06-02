# Abstract

## Objective
Summarize the motivation, proposed hierarchical token pruning method, experimental setup (NYU Depth V2, KITTI, synthetic edge set), primary results (≥30 fps at 720p on Jetson Orin Nano, ≤5 % depth error increase, 4× FLOPs and 3× memory reduction), and contributions to the 2023‑2025 monocular depth estimation literature.

## Draft
Draft this section by focusing on: Summarize the motivation, proposed hierarchical token pruning method, experimental setup (NYU Depth V2, KITTI, synthetic edge set), primary results (≥30 fps at 720p on Jetson Orin Nano, ≤5 % depth error increase, 4× FLOPs and 3× memory reduction), and contributions to the 2023‑2025 monocular depth estimation literature.. Use approved stage outputs and keep claims grounded in evidence.

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
