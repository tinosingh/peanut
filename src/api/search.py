"""POST /search — hybrid BM25 + ANN with RRF merge and CrossEncoder rerank.

Pipeline:
  1. BM25 top-50 via tsvector (pg_trgm)
  2. ANN top-50 via pgvector cosine on query embedding from Ollama
  3. RRF merge (k from config table)
  4. CrossEncoder rerank (graceful degradation if unavailable or < 5 hits)
  5. Return top-N with per-result scores + degraded flag

Caching: TTL dict keyed on (q, limit); TTL read from config.search_cache_ttl.
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx
import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.shared.config import get_config
from src.shared.reranker import rerank
from src.shared.rrf import rrf_merge, weighted_merge

log = structlog.get_logger()

router = APIRouter()

# ── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict[tuple, tuple[float, Any]] = {}  # key -> (expires_at, value)


def _cache_get(key: tuple) -> Any | None:
    entry = _cache.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    _cache.pop(key, None)
    return None


def _cache_set(key: tuple, value: Any, ttl: int) -> None:
    _cache[key] = (time.monotonic() + ttl, value)


# ── Pydantic models ───────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(10, ge=1, le=100)


class SearchResult(BaseModel):
    chunk_id: str
    doc_id: str
    source_path: str
    sender: str
    snippet: str
    bm25_score: float
    vector_score: float
    rerank_score: float


class SearchResponse(BaseModel):
    results: list[SearchResult]
    degraded: bool
    query: str


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _embed_query(query: str, model: str) -> list[float] | None:
    """Call Ollama on host to embed the query."""
    ollama_url = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{ollama_url}/api/embeddings",
                json={"model": model, "prompt": query},
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
    except Exception as exc:
        log.warning("embed_query_failed", error=str(exc))
        return None


async def _bm25_search(conn, query: str, limit: int) -> list[tuple[str, float]]:
    """Return [(chunk_id, ts_rank)] sorted best-first."""
    rows = await conn.execute(
        """
        SELECT id::text, ts_rank(tsv, plainto_tsquery('english', %s)) AS score
        FROM chunks
        WHERE tsv @@ plainto_tsquery('english', %s)
          AND embedding_status = 'done'
          AND pii_detected = false
        ORDER BY score DESC
        LIMIT %s
        """,
        (query, query, limit),
    )
    return [(r[0], float(r[1])) for r in await rows.fetchall()]


async def _ann_search(
    conn, embedding: list[float], limit: int
) -> list[tuple[str, float]]:
    """Return [(chunk_id, cosine_similarity)] sorted best-first."""
    rows = await conn.execute(
        """
        SELECT id::text, 1 - (embedding <=> %s::vector) AS score
        FROM chunks
        WHERE embedding IS NOT NULL
          AND embedding_status = 'done'
          AND pii_detected = false
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (embedding, embedding, limit),
    )
    return [(r[0], float(r[1])) for r in await rows.fetchall()]


async def _fetch_chunk_details(
    conn, chunk_ids: list[str]
) -> dict[str, dict]:
    """Fetch text, doc metadata, and sender for given chunk IDs."""
    if not chunk_ids:
        return {}
    placeholders = ",".join(["%s"] * len(chunk_ids))
    rows = await conn.execute(
        f"""
        SELECT
            c.id::text,
            c.text,
            c.doc_id::text,
            d.source_path,
            p.email AS sender_email
        FROM chunks c
        JOIN documents d ON d.id = c.doc_id
        LEFT JOIN persons p ON p.email = (d.metadata->>'sender_email')
        WHERE c.id::text IN ({placeholders})
          AND d.deleted_at IS NULL
        """,
        chunk_ids,
    )
    result = {}
    for row in await rows.fetchall():
        chunk_id, text, doc_id, source_path, sender = row
        result[chunk_id] = {
            "text": text,
            "doc_id": doc_id,
            "source_path": source_path or "",
            "sender": sender or "—",
        }
    return result


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    import time

    from src.shared.db import get_pool
    start_time = time.time()
    cache_key = (req.q, req.limit)
    if cached := _cache_get(cache_key):
        log.info("search_cache_hit", query=req.q[:100])
        return cached

    log.info("search_started", query=req.q[:100], limit=req.limit)
    pool = await get_pool()
    cfg = await get_config(pool)

    rrf_k = int(cfg.get("rrf_k", 60))
    embed_model = str(cfg.get("embed_model", "nomic-embed-text"))
    ttl = int(cfg.get("search_cache_ttl", 60))
    bm25_weight = float(cfg.get("bm25_weight", 0.5))
    vector_weight = float(cfg.get("vector_weight", 0.5))
    use_weighted = abs(bm25_weight - 0.5) > 0.01 or abs(vector_weight - 0.5) > 0.01
    candidate_limit = 50

    degraded = False

    async with pool.connection() as conn:
        bm25_results = await _bm25_search(conn, req.q, candidate_limit)
        bm25_scores = {cid: score for cid, score in bm25_results}
        bm25_ids = [cid for cid, _ in bm25_results]

        embedding = await _embed_query(req.q, embed_model)
        ann_ids: list[str] = []
        ann_scores: dict[str, float] = {}
        if embedding:
            ann_results = await _ann_search(conn, embedding, candidate_limit)
            ann_scores = {cid: score for cid, score in ann_results}
            ann_ids = [cid for cid, _ in ann_results]
        else:
            degraded = True

        if use_weighted and ann_scores:
            merged_ids = weighted_merge(bm25_scores, ann_scores, bm25_weight, vector_weight)
        else:
            merged_ids = rrf_merge(bm25_ids, ann_ids, k=rrf_k)
        top_ids = merged_ids[: req.limit * 5]  # over-fetch for reranker

        details = await _fetch_chunk_details(conn, top_ids)

    # Filter to IDs that have details (not deleted, etc.)
    valid_ids = [cid for cid in top_ids if cid in details]

    # Rerank
    snippets = [details[cid]["text"][:500] for cid in valid_ids]
    rerank_scores_list = rerank(req.q, snippets)
    if rerank_scores_list is None:
        rerank_scores = {cid: 0.0 for cid in valid_ids}
        if len(valid_ids) >= 5:
            degraded = True
    else:
        rerank_scores = dict(zip(valid_ids, rerank_scores_list, strict=False))
        # Re-sort by rerank score descending
        valid_ids = sorted(valid_ids, key=lambda cid: rerank_scores[cid], reverse=True)

    results = []
    for cid in valid_ids[: req.limit]:
        d = details[cid]
        results.append(
            SearchResult(
                chunk_id=cid,
                doc_id=d["doc_id"],
                source_path=d["source_path"],
                sender=d["sender"],
                snippet=d["text"][:200],
                bm25_score=round(bm25_scores.get(cid, 0.0), 4),
                vector_score=round(ann_scores.get(cid, 0.0), 4),
                rerank_score=round(rerank_scores.get(cid, 0.0), 4),
            )
        )

    response = SearchResponse(results=results, degraded=degraded, query=req.q)
    _cache_set(cache_key, response, ttl)
    
    elapsed_ms = (time.time() - start_time) * 1000
    log.info("search_completed",
        result_count=len(results),
        elapsed_ms=elapsed_ms,
        degraded=degraded,
        bm25_matches=len(bm25_ids),
        ann_matches=len(ann_ids),
        merged_count=len(merged_ids),
        reranked=len(rerank_scores_list) if rerank_scores_list else 0)
    
    return response
