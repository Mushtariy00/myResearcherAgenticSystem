# Introduction

## Objective
Introduce monocular depth estimation challenges, recent transformer‑based advances (ESA‑ViT), and the need for real‑time inference on edge devices. Highlight gaps in existing surveys (2023‑2025) regarding token‑level efficiency and edge‑case robustness. State the research question and contributions of this work.

## Draft
Draft this section by focusing on: Introduce monocular depth estimation challenges, recent transformer‑based advances (ESA‑ViT), and the need for real‑time inference on edge devices. Highlight gaps in existing surveys (2023‑2025) regarding token‑level efficiency and edge‑case robustness. State the research question and contributions of this work.. Use approved stage outputs and keep claims grounded in evidence.

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
