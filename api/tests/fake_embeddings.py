"""Deterministic fake encoders for E16 tests.

The real embedding model is NEVER loaded in tests (Notes E16 in
docs/EPICS.md): these stand-ins return synthetic 1024-dim vectors. Two
flavours:

* ``HashEncoder`` — pseudo-random unit vector seeded from the text hash.
  Same text → same vector, different texts → (near-)orthogonal vectors.
  Used as the process-wide safety net in conftest and for "embedding is
  written" assertions.
* ``axis_vector`` — one-hot basis vectors for the Smart Match maths tests
  (E16-S3), where exact cosine similarities must be controlled.
"""

import hashlib

import numpy as np

from niouzou.services.embedding_service import EMBEDDING_DIM


class HashEncoder:
    """Encoder double: deterministic unit vectors, no model, no download."""

    def __init__(self) -> None:
        self.calls = 0

    def encode(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        out = []
        for text in texts:
            seed = int.from_bytes(
                hashlib.sha256(text.encode()).digest()[:8], "big"
            )
            rng = np.random.default_rng(seed)
            vec = rng.standard_normal(EMBEDDING_DIM)
            out.append(vec / np.linalg.norm(vec))
        return np.asarray(out)


def axis_vector(axis: int, dim: int = EMBEDDING_DIM) -> list[float]:
    """Unit vector along one axis — orthogonal to every other axis."""
    vec = [0.0] * dim
    vec[axis] = 1.0
    return vec


def blend_vector(axis_a: int, axis_b: int, dim: int = EMBEDDING_DIM) -> list[float]:
    """Normalised 50/50 blend of two axes (cosine ≈ 0.707 with each)."""
    vec = [0.0] * dim
    vec[axis_a] = vec[axis_b] = 1.0 / np.sqrt(2.0)
    return vec
