# 6. Results

## Objective
Present quantitative results on the two benchmark subsets, compare VDFM against MiDaS‑small baseline, include ablation studies for each loss component, and provide convergence plots (training loss, photometric loss, etc.). Highlight achievement of AbsRel ≤ 0.30.

## Draft
Draft this section by focusing on: Present quantitative results on the two benchmark subsets, compare VDFM against MiDaS‑small baseline, include ablation studies for each loss component, and provide convergence plots (training loss, photometric loss, etc.). Highlight achievement of AbsRel ≤ 0.30.. Use approved stage outputs and keep claims grounded in evidence.

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
