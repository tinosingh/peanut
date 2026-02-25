"""Reciprocal Rank Fusion + Weighted Score Fusion.

RRF (default): score = sum_over_lists( 1 / (k + rank(d)) ), k=60
Weighted fusion (Epic 4 Story 4.5): score = bm25_score × w1 + ann_score × w2
  — activated when bm25_weight + vector_weight != 1.0 or config explicitly uses it.

Config keys:
  rrf_k          — RRF constant (default 60)
  bm25_weight    — weight for BM25 scores in weighted fusion (default 0.5)
  vector_weight  — weight for ANN scores in weighted fusion (default 0.5)
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


def weighted_merge(
    bm25_scores: dict[str, float],
    ann_scores: dict[str, float],
    bm25_weight: float = 0.5,
    vector_weight: float = 0.5,
) -> list[str]:
    """Weighted score fusion: combined = bm25_score × w1 + ann_score × w2.

    Scores are min-max normalised within each list before weighting so that
    BM25 tf-idf magnitudes don't dominate ANN cosine similarities.

    Args:
        bm25_scores:   {chunk_id: bm25_score} (higher = better)
        ann_scores:    {chunk_id: cosine_similarity} (higher = better)
        bm25_weight:   weight for BM25 component (0.0–1.0)
        vector_weight: weight for ANN component (0.0–1.0)

    Returns:
        Merged list of doc IDs sorted by combined score descending.
    """
    def _normalise(scores: dict[str, float]) -> dict[str, float]:
        if not scores:
            return {}
        lo, hi = min(scores.values()), max(scores.values())
        rng = hi - lo
        if rng == 0:
            return {k: 1.0 for k in scores}
        return {k: (v - lo) / rng for k, v in scores.items()}

    norm_bm25 = _normalise(bm25_scores)
    norm_ann = _normalise(ann_scores)

    all_ids = set(norm_bm25) | set(norm_ann)
    combined: dict[str, float] = {
        doc_id: bm25_weight * norm_bm25.get(doc_id, 0.0)
                + vector_weight * norm_ann.get(doc_id, 0.0)
        for doc_id in all_ids
    }
    return sorted(combined, key=lambda d: combined[d], reverse=True)
