# Sandbox Artifact

Topic: Survey monocular depth estimation 2023-2025

Recommended method: Hybrid Conv-Transformer Lite (HCT-Lite) combined with the Self-Supervised Multi-Task Pre-Training on Large-Scale Video (SS-MTP-LTV) – this dual approach first builds a compute‑efficient backbone and then endows it with robust, multi-domain representations, directly addressing the foremost gap of edge‑friendly high‑accuracy depth estimation.

Run:
```bash
python train_lct_depth.py
python benchmark.py
```
