"""The real writing stage (docs/PLAN.md, Phase 2).

One execute_stage activity asks for an outline (title, abstract, sections), then for each
section's Markdown, one at a time, and assembles the draft. Citations are code, not trust: the
writer cites the literature output's papers by number, out-of-range markers are removed, and
the citation list and the references come from the markers the draft uses. Nothing is stored
before the output: an attempt that runs again asks again, and the gateway replays the calls it
already answered (deterministic keys) from its journal for free.
"""
