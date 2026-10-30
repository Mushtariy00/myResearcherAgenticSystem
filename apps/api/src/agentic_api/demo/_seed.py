"""Seeded randomness for the demo generators."""

import hashlib
import random


def rng_for(*parts: object) -> random.Random:
    """A random generator seeded from ``parts`` (ids, dates, sample numbers).

    The key goes through SHA-256, so seeds are stable across processes (``hash()`` is salted).
    """
    key = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(key.encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))  # noqa: S311 - demo data, not secrets
