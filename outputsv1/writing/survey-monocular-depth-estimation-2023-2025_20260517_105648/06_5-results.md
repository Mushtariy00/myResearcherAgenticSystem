# 5 Results

## Objective
Present quantitative results on all tracked metrics: training loss curves, mask activation statistics, AbsRel/SqRel/RMSE/RMSE_log/δ<1.25 for both domains, and inference latency/FPS. Compare against baseline (no mask) and relevant state‑of‑the‑art methods.

## Draft
Draft this section by focusing on: Present quantitative results on all tracked metrics: training loss curves, mask activation statistics, AbsRel/SqRel/RMSE/RMSE_log/δ<1.25 for both domains, and inference latency/FPS. Compare against baseline (no mask) and relevant state‑of‑the‑art methods.. Use approved stage outputs and keep claims grounded in evidence.

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
