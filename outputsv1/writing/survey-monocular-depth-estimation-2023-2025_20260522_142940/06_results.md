# Results

## Objective
Present quantitative results in tables/plots: baseline vs pruned models on all metrics, trade‑off curves (error vs FLOPs, FPS vs prune rate), token‑count distribution per layer, and edge‑case performance. Highlight achieving ≥30 fps, 4× FLOPs reduction, 3× memory reduction while staying within 5 % error of dense baseline.

## Draft
Draft this section by focusing on: Present quantitative results in tables/plots: baseline vs pruned models on all metrics, trade‑off curves (error vs FLOPs, FPS vs prune rate), token‑count distribution per layer, and edge‑case performance. Highlight achieving ≥30 fps, 4× FLOPs reduction, 3× memory reduction while staying within 5 % error of dense baseline.. Use approved stage outputs and keep claims grounded in evidence.

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
