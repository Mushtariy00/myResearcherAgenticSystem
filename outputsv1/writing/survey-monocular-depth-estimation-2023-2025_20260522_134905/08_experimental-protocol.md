# Experimental Protocol

## Objective
Specify the run configuration (docker_image, device, CI workflow), reproducibility steps (seed settings, deterministic ops), and procedure for reporting results to the benchmark server.

## Draft
Draft this section by focusing on: Specify the run configuration (docker_image, device, CI workflow), reproducibility steps (seed settings, deterministic ops), and procedure for reporting results to the benchmark server.. Use approved stage outputs and keep claims grounded in evidence.

## Review Focus
Ensure completeness of benchmark description, reproducibility rigor, proper justification of metric choices, and clear linkage to recent (2023‑2025) depth estimation literature. Verify that each section aligns with the experiment goal and facilitates peer review of reproducibility claims.

## Metrics to Reference
- Threshold Accuracy (δ<1.25, δ<1.25^2, δ<1.25^3)
- RMSE
- MAE
- SILog
- Inference Latency (ms per frame)
- Domain‑Shift Score (FID)
- Robustness Degradation Ratio (rain, fog, night)
- Overall Score (weighted aggregate)
