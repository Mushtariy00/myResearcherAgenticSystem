"""Deterministic demo outputs for every stage, used until the real stages are built.

Each generator is pure: the same arguments give the same output (``random.Random`` seeded from
``seed``), nothing is read or written, and the result is a validated ``agentic_core.schemas``
model. Later stages take the earlier outputs as input, so a run tells one consistent story:
the method cites the screened papers, the code implements the recommended proposal, the
experiment hashes that code, and the draft cites the papers and reports the final metrics.

The worker flags these outputs as degraded (``literature.demo_search`` / ``stage.demo``), so
nobody mistakes them for research results. Identifiers are synthetic: arXiv ids use sequence
numbers from 90000 up and DOIs use Crossref's 10.5555 test prefix.
"""

from agentic_core.demo._coding import GPU_NAME, coding
from agentic_core.demo._experiment import code_hashes, experiment
from agentic_core.demo._literature import SOURCE_LABELS, literature, research_plan
from agentic_core.demo._method import method
from agentic_core.demo._writing import writing

# Stored as stage_outputs.prompt_version; bump it when the generated outputs change shape.
PROMPT_VERSION = "demo@1"

__all__ = [
    "GPU_NAME",
    "PROMPT_VERSION",
    "SOURCE_LABELS",
    "code_hashes",
    "coding",
    "experiment",
    "literature",
    "method",
    "research_plan",
    "writing",
]
