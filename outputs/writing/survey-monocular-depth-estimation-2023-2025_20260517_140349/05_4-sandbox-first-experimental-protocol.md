# 4. Sandbox‑First Experimental Protocol

## Objective
Describe the curated video subset (5k clips, 3 s, 10 fps), COLMAP sparse depth generation, training configuration (batch size 2, LR 1e‑4, 1000 iterations, seed 42), hardware constraints, and logging/checkpointing strategy. Emphasize the “sandbox‑first” philosophy for fast iteration.

## Draft
Draft this section by focusing on: Describe the curated video subset (5k clips, 3 s, 10 fps), COLMAP sparse depth generation, training configuration (batch size 2, LR 1e‑4, 1000 iterations, seed 42), hardware constraints, and logging/checkpointing strategy. Emphasize the “sandbox‑first” philosophy for fast iteration.. Use approved stage outputs and keep claims grounded in evidence.

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
