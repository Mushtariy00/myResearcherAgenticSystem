"""The experiment stage: the approved model code trained on the lab GPU, with its real metrics.

docs/design/experiments.md ("The stages"): a bounded training plan from the approved code's
config.json and the worker's settings, its batch size sized from the smoke test's GPU memory, one
training job through the executor, and an output that mirrors the job honestly: its curves from
the executor's epoch events, its final metrics, its log tail and its provenance.
"""
