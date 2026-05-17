# 7 Discussion

## Objective
Interpret how dynamic masking mitigates moving‑object violations of photometric consistency, discuss trade‑offs between accuracy and latency, and examine generalization from static to highly dynamic domains.

## Draft
Draft this section by focusing on: Interpret how dynamic masking mitigates moving‑object violations of photometric consistency, discuss trade‑offs between accuracy and latency, and examine generalization from static to highly dynamic domains.. Use approved stage outputs and keep claims grounded in evidence.

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
