# 2 Related Work

## Objective
Review self‑supervised monocular depth methods (e.g., Zhou et al., Monodepth2), prior dynamic‑object handling techniques (optical‑flow masking, segmentation‑based), and recent surveys (2023‑2025) on depth estimation. Highlight gaps that the current work addresses.

## Draft
Draft this section by focusing on: Review self‑supervised monocular depth methods (e.g., Zhou et al., Monodepth2), prior dynamic‑object handling techniques (optical‑flow masking, segmentation‑based), and recent surveys (2023‑2025) on depth estimation. Highlight gaps that the current work addresses.. Use approved stage outputs and keep claims grounded in evidence.

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
