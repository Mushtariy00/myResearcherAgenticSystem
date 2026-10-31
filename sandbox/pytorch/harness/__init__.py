"""Training harness that runs inside the GPU sandbox.

The harness owns data loading, splits, metrics and the training loop. Generated code may only add
model and loss modules (Phase 3). Ported from main:src/agentic_ai_system/train/loop.py, minus its
silent fallbacks to "generic" modules and synthetic data.
"""

__version__ = "0.2.0"  # 0.2: the blocks generated code may import, and the smoke shape trace
