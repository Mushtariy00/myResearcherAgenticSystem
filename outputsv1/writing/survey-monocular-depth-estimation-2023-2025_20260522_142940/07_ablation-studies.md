# Ablation Studies

## Objective
Analyze impact of prune_rate, curriculum schedule, and static vs dynamic pruning on accuracy, efficiency, and edge robustness. Include per‑layer token analysis and sensitivity to synthetic edge set.

## Draft
Draft this section by focusing on: Analyze impact of prune_rate, curriculum schedule, and static vs dynamic pruning on accuracy, efficiency, and edge robustness. Include per‑layer token analysis and sensitivity to synthetic edge set.. Use approved stage outputs and keep claims grounded in evidence.

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
