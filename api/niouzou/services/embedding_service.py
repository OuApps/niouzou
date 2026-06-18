"""Local sentence-embedding service (E16-S2).

One 1024-dim vector per article, computed from ``title + summary_executive``
(or a content prefix when no summary exists) with Qwen3-Embedding-0.6B via
sentence-transformers. Vectors are L2-normalised so pgvector's ``<=>``
(cosine distance) is directly meaningful.

Process placement: only the refresh worker (cron enrichment) and the backfill
CLI ever call ``embed_*`` — the FastAPI web process must never trigger the
model load (~1.2 GB resident in fp16). The model therefore loads lazily on
the first embed call, not at import or construction time.

Instruction prompts are deliberately NOT used. Qwen3-Embedding is
instruction-aware (a query-side prefix boosts retrieval benchmarks), but our
usage is symmetric — articles are compared to other articles — so everything
is embedded uniformly in plain document mode. Do not add an instruction to
one side later: mixing vectors computed with and without an instruction
breaks their comparability, and changing the convention means a full
re-backfill.

Tests NEVER load the real model (absolute rule, see Notes E16 in
docs/EPICS.md): they inject a fake encoder via the constructor, same pattern
as ``OpenRouterClient`` in the scorers. ``api/tests/conftest.py`` installs a
process-wide fake singleton as a safety net.
"""

import importlib.util
import logging
import os
from typing import Any, Protocol

import numpy as np

logger = logging.getLogger("niouzou.embedding")

MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
EMBEDDING_DIM = 1024

# How much raw article body to embed when there is no summary_executive.
# The summary path (~100-200 words) is the normal case; this keeps the
# fallback in the same length ballpark.
_CONTENT_FALLBACK_CHARS = 1000

# Default upper bound on the embedding thread pool when auto-detecting (see
# Settings.embedding_num_threads). 4 threads already saturate this model's
# throughput on the measured hardware; going higher only consumes vCPU.
_DEFAULT_THREAD_CAP = 4


def _cgroup_cpu_quota() -> int | None:
    """Effective CPU count from the container's cgroup quota, or None.

    Containers expose the *host* core count to ``os.cpu_count()`` (48 on
    Railway) while the real allowance is the cgroup quota (e.g. 8 vCPU). torch
    sizes its OpenMP pool off the host count and oversubscribes badly — the
    whole reason embeddings crawled at ~65-142s instead of <1s.
    """
    # cgroup v2: "<quota> <period>" in microseconds, or "max <period>".
    try:
        with open("/sys/fs/cgroup/cpu.max") as fh:
            quota, period = fh.read().split()
        if quota != "max":
            return max(1, round(int(quota) / int(period)))
    except (OSError, ValueError):
        pass
    # cgroup v1: separate quota / period files.
    try:
        with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us") as fh:
            quota_us = int(fh.read())
        with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us") as fh:
            period_us = int(fh.read())
        if quota_us > 0:
            return max(1, round(quota_us / period_us))
    except (OSError, ValueError):
        pass
    return None


def _resolve_thread_count() -> int:
    """How many threads the embedding model should use.

    Explicit ``EMBEDDING_NUM_THREADS`` wins; otherwise auto-detect the cgroup
    quota and cap it at ``_DEFAULT_THREAD_CAP`` so we never oversubscribe nor
    burn vCPU-seconds for no throughput gain.
    """
    # Imported here, not at module top, so the web process never pays the
    # config import cost just to import this module (the model never loads
    # there). Cheap on the worker path.
    from niouzou.config import get_settings

    override = get_settings().embedding_num_threads
    if override and override > 0:
        return override
    detected = _cgroup_cpu_quota() or os.cpu_count() or 1
    return min(detected, _DEFAULT_THREAD_CAP)


class Encoder(Protocol):
    """The slice of the SentenceTransformer API we rely on."""

    def encode(self, texts: list[str]) -> Any:  # ndarray-like, shape (n, dim)
        ...


def embedding_available() -> bool:
    """True when the optional sentence-transformers dependency is installed.

    Used by the enrichment cron (skip embedding with a warning instead of
    crashing) and by the admin scoring_mode validation (E16-S4: refuse
    'smart' when the model can't run).
    """
    return importlib.util.find_spec("sentence_transformers") is not None


def _load_encoder() -> Encoder:
    """Load the real model. Kept module-level so tests can count calls."""
    import torch
    from sentence_transformers import SentenceTransformer

    # Cap the OpenMP/MKL pool BEFORE the model runs any op. Without this torch
    # oversubscribes the container (host cores ≫ cgroup quota) and embeddings
    # crawl (measured 142s → 0.8s/embed once capped).
    threads = _resolve_thread_count()
    torch.set_num_threads(threads)
    logger.info(
        "embedding: loading %s (first call in this process, torch_threads=%d)",
        MODEL_ID,
        threads,
    )
    # torch_dtype="auto" honours the checkpoint dtype (bf16 for Qwen3) —
    # ~1.2 GB resident instead of ~2.4 GB in fp32. If the target CPU chokes
    # on half precision, an ONNX int8 export is the documented escape hatch.
    return SentenceTransformer(MODEL_ID, model_kwargs={"torch_dtype": "auto"})


def build_article_text(
    title: str, summary_executive: str | None, content: str | None
) -> str:
    """The exact text an article's embedding is computed from.

    Title plus the executive summary (the condensed topic signal); articles
    not yet summarised fall back to a content prefix; a bare title still
    embeds fine.
    """
    summary = (summary_executive or "").strip()
    if summary:
        return f"{title} {summary}"
    body = (content or "").strip()
    if body:
        return f"{title} {body[:_CONTENT_FALLBACK_CHARS]}"
    return title


class EmbeddingService:
    def __init__(self, encoder: Encoder | None = None) -> None:
        # None → the real model, loaded lazily on first use. Tests always
        # inject a deterministic fake here.
        self._encoder = encoder
        # Injected encoders (tests) are never dropped by unload() — discarding
        # a fake would force a real model load (and trip conftest's tripwire).
        self._injected = encoder is not None

    def _get_encoder(self) -> Encoder:
        if self._encoder is None:
            self._encoder = _load_encoder()
        return self._encoder

    def unload(self) -> bool:
        """Drop a lazily-loaded model so its RAM can be reclaimed (E17-S4).

        Returns True when an actual model was released. No-op for injected
        encoders (tests) and when nothing has been loaded yet. The next embed
        call reloads lazily.
        """
        if self._injected or self._encoder is None:
            return False
        self._encoder = None
        return True

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch (one encoder call) and L2-normalise each vector.

        Normalisation happens here rather than via the encoder's own options
        so the invariant holds for any injected encoder.
        """
        if not texts:
            return []
        raw = np.asarray(self._get_encoder().encode(texts), dtype=np.float64)
        if raw.ndim != 2 or raw.shape[1] != EMBEDDING_DIM:
            raise ValueError(
                f"encoder returned shape {raw.shape}, expected (n, {EMBEDDING_DIM})"
            )
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0  # zero vector stays zero rather than NaN
        return (raw / norms).tolist()

    def embed_article(
        self, title: str, summary_executive: str | None, content: str | None
    ) -> list[float]:
        return self.embed_texts([build_article_text(title, summary_executive, content)])[0]


# Module-level singleton: the model must load at most once per process.
_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service


def unload_embedding_model() -> None:
    """Release the resident embedding model (~1.2 GB) between worker runs (E17-S4).

    The refresh worker is always-on; without this the model sits in RAM 24/7.
    Called after each fetch+enrich cycle — it reloads lazily on the next run.
    A small cold-start cost per run in exchange for near-zero idle RAM.
    """
    if _service is None:
        return
    if _service.unload():
        import gc

        gc.collect()
        logger.info("embedding: model unloaded, RAM released until next run")
