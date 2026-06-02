# 5. Datasets and Evaluation Metrics

## Objective
Explain the benchmark subsets (NYU‑Depth‑V2, KITTI Eigen split), list all tracked metrics (AbsRel, SqRel, RMSE, RMSElog, δ<1.25) and auxiliary training losses, and justify their relevance for depth quality assessment.

## Draft
Draft this section by focusing on: Explain the benchmark subsets (NYU‑Depth‑V2, KITTI Eigen split), list all tracked metrics (AbsRel, SqRel, RMSE, RMSElog, δ<1.25) and auxiliary training losses, and justify their relevance for depth quality assessment.. Use approved stage outputs and keep claims grounded in evidence.

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
