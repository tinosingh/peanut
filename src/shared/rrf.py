"""Reciprocal Rank Fusion — pure rank-position fusion (no score weights).

k=60 is the literature default. Read from config table at query time.

RRF score for doc d = sum_over_lists( 1 / (k + rank(d)) )

Weighted score fusion (BM25 × w1 + ANN × w2) is a DIFFERENT algorithm
deferred to Epic 4 Story 4.5.
"""
from __future__ import annotations


def rrf_merge(
    bm25_ids: list[str],
    ann_ids: list[str],
    k: int = 60,
) -> list[str]:
    """Merge two ranked lists using Reciprocal Rank Fusion.

    Args:
        bm25_ids: Doc IDs ranked by BM25 score (best first).
        ann_ids:  Doc IDs ranked by ANN similarity (best first).
        k:        RRF constant (default 60 per literature).

    Returns:
        Merged list of doc IDs sorted by RRF score descending.
    """
    scores: dict[str, float] = {}
    for rank, doc_id in enumerate(bm25_ids):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    for rank, doc_id in enumerate(ann_ids):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda d: scores[d], reverse=True)


def rrf_scores(
    bm25_ids: list[str],
    ann_ids: list[str],
    k: int = 60,
) -> dict[str, float]:
    """Return the RRF score dict (doc_id -> score) for debugging."""
    scores: dict[str, float] = {}
    for rank, doc_id in enumerate(bm25_ids):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    for rank, doc_id in enumerate(ann_ids):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return scores
