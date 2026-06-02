# Pipeline Architecture

## Objective
Describe the end‑to‑end sandbox design: PDF ingestion, LLM‑driven attribute extraction via LangChain prompts, schema validation, SQLite storage, and taxonomy visualisation. Include a diagram of the data flow and component interactions.

## Draft
Draft this section by focusing on: Describe the end‑to‑end sandbox design: PDF ingestion, LLM‑driven attribute extraction via LangChain prompts, schema validation, SQLite storage, and taxonomy visualisation. Include a diagram of the data flow and component interactions.. Use approved stage outputs and keep claims grounded in evidence.

## Review Focus
Assess whether the proposed sections collectively cover (a) the motivation for an automated survey, (b) a complete technical description of the sandbox pipeline, (c) a rigorous experimental validation achieving ≥ 90 % extraction precision, and (d) reproducibility evidence (environment spec, CI workflow, data schema). Reviewers should check clarity, logical flow, completeness of implementation details, and adequacy of quantitative results.

## Metrics to Reference
- extraction_precision_percentage
- schema_validation_success_rate
- taxonomy_generation_success
- ci_pipeline_pass_rate
- pipeline_runtime_seconds
- manual_spotcheck_accuracy
