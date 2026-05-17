# Writing Plan Summary

**Topic:** Survey monocular depth estimation 2023-2025
**Output format:** A manuscript outline ready for a journal/conference submission (IEEE Transactions on Pattern Analysis and Machine Intelligence or CVPR) with fully fleshed section objectives, suitable for direct expansion into LaTeX.
**Review focus:** Assess completeness of the trade‑off analysis, relevance of the selected datasets and metrics, rigor of the benchmarking methodology on Snapdragon 8 Gen 2, and clarity of the contribution relative to existing monocular depth surveys (2023‑2025).

## Sections
- Abstract: Summarize the motivation (real‑time monocular depth on edge GPUs), the novelty (systematic evaluation of token sparsification ratios on LCT‑Depth), key experimental settings (Snapdragon 8 Gen 2, weather‑augmented KITTI/NYU/DrivingDepth), and headline results (trade‑off curves, latency ≤30 ms with ≤5 % RMSE loss).
- Introduction: Introduce monocular depth estimation, challenges on embedded GPUs, related sparsification techniques, and the specific research gap (lack of quantitative trade‑off analysis for token sparsification on modern mobile AI accelerators). State contributions: (1) benchmark suite, (2) token‑ratio schedule study, (3) fallback branch analysis, (4) open‑source reproducible pipeline.
- Related Work: Review recent (2023‑2025) depth estimation surveys, lightweight ViT models, token pruning/sparsification, and hardware‑aware NAS for mobile GPUs. Position the current work relative to prior surveys and highlight how it extends them with empirical edge‑device evaluation.
- Methodology: Describe the LCT‑Depth architecture, token sparsification mechanism, token_ratio_schedule, loss functions (scale‑invariant log‑RMSE, edge‑aware gradient), optimizer settings, and the fallback branch design. Include a diagram of the training/inference pipeline on Snapdragon 8 Gen 2.
- Experimental Setup: Detail dataset preparation (weather augmentation for DrivingDepth, splits), hardware and software stack (Docker Ubuntu 22.04, CUDA 12.1, ONNX Runtime/TensorRT, mixed precision, gradient checkpointing), training hyper‑parameters, benchmark protocol (100 runs, latency & throughput measurement), and evaluation metrics as listed.
- Results: Present quantitative findings: (a) validation loss and depth accuracy across token ratios, (b) latency and FLOPs reductions, (c) trade‑off curves versus baseline, (d) impact of fallback branch usage, and (e) robustness across weather conditions. Use tables and plots (RMSE% vs latency%, token count reduction).
- Ablation Studies: Isolate effects of (i) token_ratio_schedule, (ii) mixed‑precision vs full‑precision, (iii) gradient checkpointing, and (iv) different loss term weightings. Report statistical significance and early‑stop behavior.
- Discussion: Interpret the trade‑offs, discuss practical implications for AR/ADAS deployments, limitations (e.g., dataset bias, single‑GPU focus), and potential extensions (dynamic token ratio, multimodal inputs).
- Conclusion & Future Work: Recap key insights, reaffirm contributions, and outline future directions such as adaptive sparsification, broader hardware benchmarks, and integration into end‑to‑end perception stacks.
- Reproducibility Statement: Provide URLs for code, Dockerfile, ONNX models, dataset split definitions, and random seed configurations to ensure repeatability.
- References: Cite all surveyed works (2023‑2025 depth estimation surveys), LCT‑Depth paper, token pruning literature, and hardware‑aware inference frameworks.
