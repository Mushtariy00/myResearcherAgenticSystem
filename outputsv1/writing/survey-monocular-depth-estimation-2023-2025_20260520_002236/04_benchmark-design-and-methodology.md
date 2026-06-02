# Benchmark Design and Methodology

## Objective
Detail the experimental setup: datasets (Waymo Open Motion, TartanAir), HCT‑Lite architecture, training curriculum, loss composition, hardware proxy (Snapdragon 8‑Gen 2 GPU), software stack (Docker, PyTorch 2.3, ONNX), and evaluation protocol (metrics, latency thresholds, test‑time adaptive token pruning).

## Draft
Draft this section by focusing on: Detail the experimental setup: datasets (Waymo Open Motion, TartanAir), HCT‑Lite architecture, training curriculum, loss composition, hardware proxy (Snapdragon 8‑Gen 2 GPU), software stack (Docker, PyTorch 2.3, ONNX), and evaluation protocol (metrics, latency thresholds, test‑time adaptive token pruning).. Use approved stage outputs and keep claims grounded in evidence.

## Review Focus
Emphasize completeness of the literature survey (2023‑2025), rigor of the benchmarking methodology, reproducibility of the experimental pipeline, and clarity of the performance‑vs‑latency trade‑off analysis.

## Metrics to Reference
- Inference latency (ms)
- AbsRel
- SqRel
- RMSE
- Delta <1.25
- Training photometric loss
- Auxiliary semantic loss
- Auxiliary normal loss
- GPU memory usage (MiB)
- Training step throughput (frames/s)
- ONNX export latency difference (ms)
