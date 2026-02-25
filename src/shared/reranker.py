"""CrossEncoder reranker — loaded lazily in-process in tui-controller.

Model: cross-encoder/ms-marco-MiniLM-L6-v2
Memory budget: ~350 MB (tui-controller peak ~850 MB including baseline)

Graceful degradation: if model unavailable, returns None scores.
Reranking skipped for < 5 results (not worth the latency).
"""
from __future__ import annotations

import functools

import structlog

log = structlog.get_logger()

_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L6-v2"


@functools.lru_cache(maxsize=1)
def _get_reranker():
    try:
        from sentence_transformers import CrossEncoder
        model = CrossEncoder(model_name=_MODEL_NAME)
        log.info("reranker_loaded", model=_MODEL_NAME)
        return model
    except Exception as exc:
        log.warning("reranker_unavailable", error=str(exc))
        return None


def rerank(
    query: str,
    candidates: list[str],
) -> list[float] | None:
    """Rerank candidates for query. Returns scores or None if unavailable.

    Returns None (triggering graceful degradation) when:
    - sentence-transformers not installed
    - < 5 candidates (not worth latency)
    - model loading failed
    """
    if len(candidates) < 5:
        return None

    model = _get_reranker()
    if model is None:
        return None

    pairs = [(query, c) for c in candidates]
    try:
        scores = model.predict(pairs)
        return scores.tolist()
    except Exception as exc:
        log.error("reranker_predict_failed", error=str(exc))
        return None
