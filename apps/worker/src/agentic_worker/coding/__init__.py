"""The coding stage: model code from the approved method, checked and smoke-tested on the GPU.

docs/design/experiments.md ("The stages"): the LLM writes model.py (and loss.py) to the harness's
generated-code contract, the allowlist checker reads it, and a dry run on the GPU (a smoke job)
tries it; a failure goes back to the LLM, at most 3 tries in all.
"""
