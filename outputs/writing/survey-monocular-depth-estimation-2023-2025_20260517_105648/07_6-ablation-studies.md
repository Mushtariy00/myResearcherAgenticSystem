# 6 Ablation Studies

## Objective
Analyze the impact of each training phase, mask regularization weight, and pseudo‑mask quality. Provide visual examples of depth maps, dynamic masks, and pose trajectories to illustrate qualitative improvements.

## Draft
Draft this section by focusing on: Analyze the impact of each training phase, mask regularization weight, and pseudo‑mask quality. Provide visual examples of depth maps, dynamic masks, and pose trajectories to illustrate qualitative improvements.. Use approved stage outputs and keep claims grounded in evidence.

## Review Focus
Emphasize methodological rigor (training phases, loss design), reproducibility (docker image, dataset splits, code scripts), and performance validation (both accuracy metrics and real‑time inference benchmarks) to satisfy reviewers interested in practical self‑supervised depth estimation for dynamic scenes.

## Metrics to Reference
- Training loss (photometric)
- Mask activation mean
- AbsRel (KITTI test)
- AbsRel (SoccerNet held‑out)
- Δ<1.25 accuracy (both domains)
- Inference latency (ms per frame)
- FPS on edge hardware
