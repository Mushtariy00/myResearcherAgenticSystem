"""Resource budgets the harness enforces on generated models, kept apart so they are easy to find."""

from __future__ import annotations

# A generated model may have at most this many parameters. The dev GPU is a 6 GB GTX 1060, so a
# larger model would not train; the smoke test rejects it before any GPU time is spent.
MAX_PARAMS = 50_000_000
