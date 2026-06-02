# 4 Experimental Setup

## Objective
Describe datasets (KITTI train/test subsets, SoccerNet clip/held‑out), preprocessing (384×1280 resolution, batch size 8), optimizer settings, hardware (Jetson‑Orin Nano), and evaluation protocol (metrics list, visualizations). Include implementation details such as Docker image and export to TorchScript.

## Draft
Draft this section by focusing on: Describe datasets (KITTI train/test subsets, SoccerNet clip/held‑out), preprocessing (384×1280 resolution, batch size 8), optimizer settings, hardware (Jetson‑Orin Nano), and evaluation protocol (metrics list, visualizations). Include implementation details such as Docker image and export to TorchScript.. Use approved stage outputs and keep claims grounded in evidence.

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
