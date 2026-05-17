# Background & Problem Definition

## Objective
Define monocular depth estimation, key evaluation metrics, and formalize the source‑target domain shift problem (KITTI → broadcast‑video/SoccerNet).

## Draft
Draft this section by focusing on: Define monocular depth estimation, key evaluation metrics, and formalize the source‑target domain shift problem (KITTI → broadcast‑video/SoccerNet).. Use approved stage outputs and keep claims grounded in evidence.

## Review Focus
Assess novelty of the adapter‑MAML pipeline, reproducibility of the experimental setup (docker image, hyper‑parameters, dataset splits), rigor of the evaluation (statistical significance, scale‑consistency tolerance), and clarity of the survey’s integration with the empirical study.

## Metrics to Reference
- Abs Rel (KITTI validation)
- Sq Rel (KITTI validation)
- RMSE (KITTI validation)
- Abs Rel (SoccerNet test)
- Sq Rel (SoccerNet test)
- RMSE (SoccerNet test)
- Scale consistency error (median depth ratio)
- Adapter inner‑loop loss
- Meta‑validation loss
- Training wall‑clock time
