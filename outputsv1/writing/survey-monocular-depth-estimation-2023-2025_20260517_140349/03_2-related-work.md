# 2. Related Work

## Objective
Survey recent monocular depth estimation approaches (Transformer‑based, CNN‑based, hybrid), self‑supervised training strategies, and benchmark datasets (NYU‑Depth‑V2, KITTI). Compare VDFM to MiDaS‑small and position the work within the 2023‑2025 literature landscape.

## Draft
Draft this section by focusing on: Survey recent monocular depth estimation approaches (Transformer‑based, CNN‑based, hybrid), self‑supervised training strategies, and benchmark datasets (NYU‑Depth‑V2, KITTI). Compare VDFM to MiDaS‑small and position the work within the 2023‑2025 literature landscape.. Use approved stage outputs and keep claims grounded in evidence.

## Review Focus
Reproducibility of the sandbox pipeline, fidelity of self‑supervised training on limited video data, quantitative depth accuracy versus MiDaS‑small, and thorough ablation of loss components. Reviewers should verify that reported metrics (AbsRel, SqRel, RMSE, RMSElog, δ<1.25) are computed on the exact benchmark subsets and that all code/configuration details are publicly available.

## Metrics to Reference
- training_loss
- photometric_loss
- sparse_depth_consistency_loss
- edge_aware_smoothness_loss
- AbsRel
- SqRel
- RMSE
- RMSElog
- delta<1.25
