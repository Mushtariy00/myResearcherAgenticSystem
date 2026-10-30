"""The real method stage (docs/PLAN.md, Phase 2).

One execute_stage activity asks one agent for research gaps and method proposals, grounded in
the approved literature review. Evidence may name only the review's papers, and the recommended
option must be one of the proposals. Nothing is stored before the output: an attempt that runs
again asks again, and the gateway replays the answer from its journal for free.
"""
