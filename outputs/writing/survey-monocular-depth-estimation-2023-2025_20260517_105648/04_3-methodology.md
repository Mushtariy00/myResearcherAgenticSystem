# 3 Methodology

## Objective
Detail the network architecture (ResNet‑18 encoder, depth/pose heads, shallow dynamic‑mask decoder), loss formulation (photometric, mask‑weighted, regularization, pose refinement), and the three‑phase training schedule. Explain pseudo‑mask generation via optical‑flow magnitude and its integration.

## Draft
Draft this section by focusing on: Detail the network architecture (ResNet‑18 encoder, depth/pose heads, shallow dynamic‑mask decoder), loss formulation (photometric, mask‑weighted, regularization, pose refinement), and the three‑phase training schedule. Explain pseudo‑mask generation via optical‑flow magnitude and its integration.. Use approved stage outputs and keep claims grounded in evidence.

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
