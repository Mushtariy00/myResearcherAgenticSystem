# Writing Plan Summary

**Topic:** Survey monocular depth estimation 2023-2025
**Output format:** The plan should be delivered as a structured JSON object (as shown) that can be directly consumed by a manuscript‑generation pipeline.
**Review focus:** Emphasize completeness of the literature survey (2023‑2025), rigor of the benchmarking methodology, reproducibility of the experimental pipeline, and clarity of the performance‑vs‑latency trade‑off analysis.

## Sections
- Abstract: Summarize the motivation, scope (2023‑2025 monocular depth literature), the introduced HCT‑Lite benchmark, key results (≤0.12 AbsRel, ≤35 ms latency), and contributions.
- Introduction: Introduce monocular depth estimation, highlight the surge of lightweight self‑supervised models (2023‑2025), state the gap in systematic benchmarking on video‑centric datasets, and outline our contributions and experiment goal.
- Background & Related Work: Survey recent monocular depth methods (self‑supervised, transformer‑based, CNN‑lightweight) published 2023‑2025, categorize by supervision, architecture, and efficiency metrics; discuss benchmark datasets and existing latency‑aware evaluations.
- Benchmark Design and Methodology: Detail the experimental setup: datasets (Waymo Open Motion, TartanAir), HCT‑Lite architecture, training curriculum, loss composition, hardware proxy (Snapdragon 8‑Gen 2 GPU), software stack (Docker, PyTorch 2.3, ONNX), and evaluation protocol (metrics, latency thresholds, test‑time adaptive token pruning).
- Implementation Details: Provide reproducible specifics: Docker image, Python/ CUDA / PyTorch versions, data loading pipelines, batch‑size, fp16 precision, optimizer schedule, checkpointing, logging (W&B), and CI pipeline fail‑conditions.
- Results: Present quantitative results on AbsRel, SqRel, RMSE, Δ<1.25, inference latency, GPU memory, throughput, and ONNX export latency. Include ablation on auxiliary losses and token pruning, and compare against state‑of‑the‑art 2023‑2025 models.
- Discussion: Interpret findings: trade‑offs between accuracy and latency, impact of curriculum and auxiliary heads, limitations of current benchmarks, and implications for edge deployment.
- Conclusion and Future Work: Recap contributions, affirm that HCT‑Lite meets the target benchmark, and propose extensions (larger video corpora, real‑world mobile inference, adaptive pruning strategies).
- Appendix: Supply full training logs, hyper‑parameter tables, additional visualizations, and the CI script for reproducibility.
