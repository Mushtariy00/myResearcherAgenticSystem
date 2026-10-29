from __future__ import annotations


class CheckpointRejected(RuntimeError):
    """Raised when user rejects a checkpoint and flow should stop gracefully."""
