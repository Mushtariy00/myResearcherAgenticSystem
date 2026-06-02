# Methodology

## Objective
Detail the ESA‑ViT architecture, the hierarchical token pruning mechanism, curriculum schedule (linear 0→0.4 over epochs 0‑20), and training regime (50 epochs, LR=1e‑4, batch‑size 8, L1+SSIM loss). Explain experimental configurations: prune rates, static vs dynamic, and hardware setup (Docker image, Jetson Orin Nano).

## Draft
Draft this section by focusing on: Detail the ESA‑ViT architecture, the hierarchical token pruning mechanism, curriculum schedule (linear 0→0.4 over epochs 0‑20), and training regime (50 epochs, LR=1e‑4, batch‑size 8, L1+SSIM loss). Explain experimental configurations: prune rates, static vs dynamic, and hardware setup (Docker image, Jetson Orin Nano).. Use approved stage outputs and keep claims grounded in evidence.

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
