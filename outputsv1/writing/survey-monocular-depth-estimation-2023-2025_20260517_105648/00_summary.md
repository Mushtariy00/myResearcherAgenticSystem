# Writing Plan Summary

**Topic:** Survey monocular depth estimation 2023-2025
**Output format:** The plan is delivered as structured JSON suitable for direct ingestion into a manuscript drafting tool.
**Review focus:** Emphasize methodological rigor (training phases, loss design), reproducibility (docker image, dataset splits, code scripts), and performance validation (both accuracy metrics and real‑time inference benchmarks) to satisfy reviewers interested in practical self‑supervised depth estimation for dynamic scenes.

## Sections
- Abstract: Summarize the motivation, proposed dynamic‑object mask, experimental setup across KITTI and SoccerNet, key quantitative improvements (e.g., ΔAbsRel), and real‑time inference results on Jetson‑Orin Nano.
- 1 Introduction: Introduce monocular depth estimation, challenges posed by dynamic scenes, and the need for lightweight, real‑time solutions. State the specific research question: can a learned dynamic‑object mask improve self‑supervised depth while preserving latency?
- 2 Related Work: Review self‑supervised monocular depth methods (e.g., Zhou et al., Monodepth2), prior dynamic‑object handling techniques (optical‑flow masking, segmentation‑based), and recent surveys (2023‑2025) on depth estimation. Highlight gaps that the current work addresses.
- 3 Methodology: Detail the network architecture (ResNet‑18 encoder, depth/pose heads, shallow dynamic‑mask decoder), loss formulation (photometric, mask‑weighted, regularization, pose refinement), and the three‑phase training schedule. Explain pseudo‑mask generation via optical‑flow magnitude and its integration.
- 4 Experimental Setup: Describe datasets (KITTI train/test subsets, SoccerNet clip/held‑out), preprocessing (384×1280 resolution, batch size 8), optimizer settings, hardware (Jetson‑Orin Nano), and evaluation protocol (metrics list, visualizations). Include implementation details such as Docker image and export to TorchScript.
- 5 Results: Present quantitative results on all tracked metrics: training loss curves, mask activation statistics, AbsRel/SqRel/RMSE/RMSE_log/δ<1.25 for both domains, and inference latency/FPS. Compare against baseline (no mask) and relevant state‑of‑the‑art methods.
- 6 Ablation Studies: Analyze the impact of each training phase, mask regularization weight, and pseudo‑mask quality. Provide visual examples of depth maps, dynamic masks, and pose trajectories to illustrate qualitative improvements.
- 7 Discussion: Interpret how dynamic masking mitigates moving‑object violations of photometric consistency, discuss trade‑offs between accuracy and latency, and examine generalization from static to highly dynamic domains.
- 8 Conclusion and Future Work: Recap contributions, confirm that the mask improves depth accuracy while meeting real‑time constraints, and outline extensions (e.g., multi‑scale masks, transformer encoders, broader dynamic datasets).
- References: Cite all surveyed works (2023‑2025), baseline methods, and datasets used.
- Appendix: Provide additional training curves, hyper‑parameter tables, and full TorchScript export script.
