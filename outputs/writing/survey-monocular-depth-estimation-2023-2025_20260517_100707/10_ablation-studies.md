# Ablation Studies

## Objective
Deep‑dive into the impact of adapter placement, bottleneck size, inner‑loop steps, and loss‑weight configurations on both domains.

## Draft
Draft this section by focusing on: Deep‑dive into the impact of adapter placement, bottleneck size, inner‑loop steps, and loss‑weight configurations on both domains.. Use approved stage outputs and keep claims grounded in evidence.

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
