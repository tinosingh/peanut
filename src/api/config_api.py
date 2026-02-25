"""Config API — read and write runtime config; PII report; bulk redact.

T-043: GET /pii/report, POST /pii/bulk-redact
T-044: GET /config, POST /config (writes bm25_weight/vector_weight)
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = structlog.get_logger()

router = APIRouter()


class WeightUpdate(BaseModel):
    bm25_weight: float
    vector_weight: float


@router.get("/config")
async def get_config_endpoint() -> dict:
    """Return all config keys."""
    from src.shared.config import get_config
    from src.shared.db import get_pool
    pool = await get_pool()
    return await get_config(pool)


@router.post("/config")
async def update_config(weights: WeightUpdate) -> dict:
    """Update bm25_weight and vector_weight in config table."""
    if not (0.0 <= weights.bm25_weight <= 1.0 and 0.0 <= weights.vector_weight <= 1.0):
        raise HTTPException(status_code=422, detail="Weights must be between 0.0 and 1.0")

    from src.shared.db import get_pool
    pool = await get_pool()
    async with pool.connection() as conn:
        for key, val in [("bm25_weight", weights.bm25_weight), ("vector_weight", weights.vector_weight)]:
            await conn.execute(
                "UPDATE config SET value = %s, updated_at = now() WHERE key = %s",
                (str(val), key),
            )
    log.info("config_updated", bm25=weights.bm25_weight, vec=weights.vector_weight)
    return {"bm25_weight": weights.bm25_weight, "vector_weight": weights.vector_weight}


@router.get("/pii/report")
async def pii_report() -> dict:
    """Return persons with pii=true and chunks with pii_detected=true."""
    from src.shared.db import get_pool
    pool = await get_pool()
    async with pool.connection() as conn:
        persons = await (await conn.execute(
            """
            SELECT p.id::text, p.display_name, p.email,
                   COUNT(DISTINCT d.id) AS doc_count
            FROM persons p
            LEFT JOIN documents d ON d.metadata->>'sender_email' = p.email
              AND d.deleted_at IS NULL
            WHERE p.pii = true AND p.deleted_at IS NULL
            GROUP BY p.id, p.display_name, p.email
            ORDER BY doc_count DESC
            LIMIT 100
            """
        )).fetchall()
        chunks = await (await conn.execute(
            """
            SELECT c.id::text, c.text, c.doc_id::text
            FROM chunks c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.pii_detected = true AND d.deleted_at IS NULL
            ORDER BY c.id
            LIMIT 200
            """
        )).fetchall()

    return {
        "persons": [
            {"id": r[0], "display_name": r[1], "email": r[2], "doc_count": r[3]}
            for r in persons
        ],
        "pii_chunks": [
            {"id": r[0], "text": r[1][:200], "doc_id": r[2]}
            for r in chunks
        ],
    }


@router.post("/pii/mark-public/{person_id}")
async def mark_public(person_id: str) -> dict:
    """Mark a person as pii=false (public figure)."""
    from src.shared.db import get_pool
    pool = await get_pool()
    async with pool.connection() as conn:
        result = await conn.execute(
            "UPDATE persons SET pii = false WHERE id = %s::uuid AND deleted_at IS NULL RETURNING id",
            (person_id,),
        )
        if not await result.fetchone():
            raise HTTPException(status_code=404, detail="Person not found")
    return {"person_id": person_id, "pii": False}


@router.post("/pii/bulk-redact")
async def bulk_redact(batch_size: int = 1000) -> dict:
    """Replace text in pii_detected=true chunks with [REDACTED], in batches."""
    from src.shared.db import get_pool
    pool = await get_pool()
    batch_size = min(max(1, batch_size), 10_000)
    total = 0
    while True:
        async with pool.connection() as conn:
            result = await conn.execute(
                """UPDATE chunks SET text = '[REDACTED]'
                WHERE id IN (
                    SELECT id FROM chunks
                    WHERE pii_detected = true AND text != '[REDACTED]'
                    LIMIT %s
                )""",
                (batch_size,),
            )
            count = result.rowcount if hasattr(result, "rowcount") else 0
        total += count
        if count < batch_size:
            break
    log.info("bulk_redact_complete", count=total)
    return {"redacted": total}
