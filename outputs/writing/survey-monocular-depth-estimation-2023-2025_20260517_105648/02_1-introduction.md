# 1 Introduction

## Objective
Introduce monocular depth estimation, challenges posed by dynamic scenes, and the need for lightweight, real‑time solutions. State the specific research question: can a learned dynamic‑object mask improve self‑supervised depth while preserving latency?

## Draft
Draft this section by focusing on: Introduce monocular depth estimation, challenges posed by dynamic scenes, and the need for lightweight, real‑time solutions. State the specific research question: can a learned dynamic‑object mask improve self‑supervised depth while preserving latency?. Use approved stage outputs and keep claims grounded in evidence.

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
