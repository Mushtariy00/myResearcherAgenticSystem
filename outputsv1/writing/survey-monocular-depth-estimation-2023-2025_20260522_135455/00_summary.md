# Writing Plan Summary

**Topic:** Survey monocular depth estimation 2023-2025
**Output format:** The plan should be rendered as a concise JSON object (as shown) suitable for direct ingestion by a project‑management tool. Each section entry contains a clear name and a one‑sentence objective.
**Review focus:** Assess whether the proposed sections collectively cover (a) the motivation for an automated survey, (b) a complete technical description of the sandbox pipeline, (c) a rigorous experimental validation achieving ≥ 90 % extraction precision, and (d) reproducibility evidence (environment spec, CI workflow, data schema). Reviewers should check clarity, logical flow, completeness of implementation details, and adequacy of quantitative results.

## Sections
- Introduction: Introduce the need for an up‑to‑date survey of monocular depth estimation (MDE) papers from 2023‑2025, highlight the rapid methodological diversity, and motivate a reproducible, automated extraction pipeline as the contribution of this work.
- Related Work: Summarize existing MDE surveys and benchmarking efforts, emphasizing gaps in systematic data collection, taxonomy construction, and reproducibility that the proposed sandbox addresses.
- Pipeline Architecture: Describe the end‑to‑end sandbox design: PDF ingestion, LLM‑driven attribute extraction via LangChain prompts, schema validation, SQLite storage, and taxonomy visualisation. Include a diagram of the data flow and component interactions.
- Implementation Details: Provide concrete technical specifications: environment (Python 3.11, dependencies file), LLM provider selection (GPT‑4o vs open‑source alternative), prompt templates, SQLite schema, JSON taxonomy output format, and CI configuration (.github/workflows/sandbox_ci.yml).
- Experimental Setup: Explain the selection of the 10‑paper sample set, the creation of a gold‑standard annotation for precision evaluation, and the metrics tracked (extraction_precision_percentage, schema_validation_success_rate, etc.).
- Results: Report quantitative outcomes: extraction precision (≥ 90 %), schema validation rate, taxonomy generation success, CI pass rate, runtime statistics, and manual spot‑check findings. Include tables and plots to illustrate performance across metrics.
- Discussion: Interpret results, discuss failure modes (e.g., ambiguous PDF layouts, LLM hallucinations), compare with manual survey efforts, and outline how the taxonomy can be extended to future years or other vision tasks.
- Conclusion and Future Work: Summarize contributions, reaffirm the reproducibility claim, and propose next steps: scaling to the full 2023‑2025 corpus, integrating multimodal LLMs, and community‑driven taxonomy enrichment.
