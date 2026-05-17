# Abstract

## Objective
Summarize the motivation, proposed dynamic‑object mask, experimental setup across KITTI and SoccerNet, key quantitative improvements (e.g., ΔAbsRel), and real‑time inference results on Jetson‑Orin Nano.

## Draft
Draft this section by focusing on: Summarize the motivation, proposed dynamic‑object mask, experimental setup across KITTI and SoccerNet, key quantitative improvements (e.g., ΔAbsRel), and real‑time inference results on Jetson‑Orin Nano.. Use approved stage outputs and keep claims grounded in evidence.

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
