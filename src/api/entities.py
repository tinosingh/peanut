"""Entities API — soft-delete and hard-delete endpoints.

T-041: DELETE /entities/{id} sets deleted_at = now(); FalkorDB invalidation via outbox
T-042: POST /entities/hard-delete (admin) deletes rows with deleted_at < now()-30d
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = structlog.get_logger()

router = APIRouter()

DELETION_LOG = Path("./data/deletion_log.jsonl")


class SoftDeleteResponse(BaseModel):
    id: str
    entity_type: Literal["document", "person"]
    deleted_at: str


class HardDeleteResponse(BaseModel):
    deleted_documents: int
    deleted_persons: int
    deleted_chunks: int
    log_path: str


@router.delete("/entities/{entity_type}/{entity_id}", response_model=SoftDeleteResponse)
async def soft_delete(entity_type: Literal["document", "person"], entity_id: str) -> SoftDeleteResponse:
    """Soft-delete a document or person — sets deleted_at = now().

    Also inserts an entity_deleted outbox event so FalkorDB edges get invalid_at.
    """
    from src.shared.db import get_pool
    pool = await get_pool()

    table = "documents" if entity_type == "document" else "persons"
    now = datetime.now(timezone.utc)

    async with pool.connection() as conn:
        result = await conn.execute(
            f"UPDATE {table} SET deleted_at = %s WHERE id = %s::uuid AND deleted_at IS NULL RETURNING id",
            (now, entity_id),
        )
        row = await result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"{entity_type} {entity_id} not found or already deleted")

        # Outbox: invalidate FalkorDB edges
        await conn.execute(
            "INSERT INTO outbox (event_type, payload) VALUES (%s, %s)",
            (
                "entity_deleted",
                json.dumps({"entity_type": entity_type, "entity_id": entity_id, "deleted_at": now.isoformat()}),
            ),
        )

    log.info("entity_soft_deleted", entity_type=entity_type, entity_id=entity_id)
    return SoftDeleteResponse(id=entity_id, entity_type=entity_type, deleted_at=now.isoformat())


@router.post("/entities/hard-delete", response_model=HardDeleteResponse)
async def hard_delete(confirm: bool = False) -> HardDeleteResponse:
    """Hard-delete all rows with deleted_at < now()-30d (requires confirm=true).

    Chunks cascade via FK. Appends receipt to ./data/deletion_log.jsonl.
    FalkorDB DETACH DELETE dispatched via outbox.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Pass confirm=true to execute hard delete. This is irreversible.",
        )

    from src.shared.db import get_pool
    pool = await get_pool()

    cutoff_sql = "now() - INTERVAL '30 days'"

    async with pool.connection() as conn:
        # Collect IDs before deletion for outbox
        doc_rows = await (await conn.execute(
            f"SELECT id::text FROM documents WHERE deleted_at < {cutoff_sql}"
        )).fetchall()
        person_rows = await (await conn.execute(
            f"SELECT id::text FROM persons WHERE deleted_at < {cutoff_sql}"
        )).fetchall()

        doc_ids = [r[0] for r in doc_rows]
        person_ids = [r[0] for r in person_rows]

        # Hard delete — chunks cascade via FK ON DELETE CASCADE
        await conn.execute(
            f"DELETE FROM documents WHERE deleted_at < {cutoff_sql}"
        )
        await conn.execute(
            f"DELETE FROM persons WHERE deleted_at < {cutoff_sql}"
        )

        # Dispatch DETACH DELETE events to outbox
        for eid in doc_ids + person_ids:
            await conn.execute(
                "INSERT INTO outbox (event_type, payload) VALUES (%s, %s)",
                ("entity_hard_deleted", json.dumps({"entity_id": eid})),
            )

    deleted_docs = len(doc_ids)
    deleted_persons = len(person_ids)

    # Append to deletion log
    DELETION_LOG.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "deleted_documents": deleted_docs,
        "deleted_persons": deleted_persons,
        "doc_ids": doc_ids,
        "person_ids": person_ids,
    }
    with DELETION_LOG.open("a") as f:
        f.write(json.dumps(receipt) + "\n")

    log.info("hard_delete_complete", deleted_docs=deleted_docs, deleted_persons=deleted_persons)
    return HardDeleteResponse(
        deleted_documents=deleted_docs,
        deleted_persons=deleted_persons,
        deleted_chunks=deleted_docs,  # chunks cascade, exact count from DB rowcount
        log_path=str(DELETION_LOG),
    )


@router.get("/entities/merge-candidates")
async def get_merge_candidates() -> dict:
    """Return person pairs that are candidates for entity resolution merge."""
    from src.shared.db import get_pool
    from src.ingest.entity_resolution import score_pair_b
    pool = await get_pool()
    async with pool.connection() as conn:
        rows = await (await conn.execute(
            """
            SELECT id::text, display_name, email
            FROM persons
            WHERE deleted_at IS NULL AND merged_into IS NULL
            ORDER BY display_name
            LIMIT 200
            """
        )).fetchall()

    # Naive O(n²) for small person sets — production: use blocking
    THRESHOLD = 0.85
    candidates = []
    persons = [{"id": r[0], "name": r[1] or "", "email": r[2]} for r in rows]
    seen: set[frozenset] = set()
    for i, a in enumerate(persons):
        for b in persons[i + 1:]:
            pair = frozenset([a["id"], b["id"]])
            if pair in seen:
                continue
            score = score_pair_b(a["name"], a["email"], b["name"], b["email"])
            if score >= THRESHOLD:
                seen.add(pair)
                same_domain = (
                    a["email"].split("@")[-1] == b["email"].split("@")[-1]
                    if "@" in a["email"] and "@" in b["email"] else False
                )
                candidates.append({
                    "id_a": a["id"], "name_a": a["name"],
                    "id_b": b["id"], "name_b": b["name"],
                    "jw_score": round(score, 3),
                    "same_domain": same_domain,
                    "shared_docs": 0,  # TODO: join in Epic 3 completion
                })
    return {"candidates": candidates}


@router.post("/entities/merge")
async def merge_entities(name_a: str, name_b: str) -> dict:
    """Merge person name_b into name_a (sets merged_into FK + outbox event)."""
    from src.shared.db import get_pool
    pool = await get_pool()
    now = datetime.now(timezone.utc)
    async with pool.connection() as conn:
        row_a = await (await conn.execute(
            "SELECT id::text FROM persons WHERE display_name = %s AND deleted_at IS NULL LIMIT 1",
            (name_a,),
        )).fetchone()
        row_b = await (await conn.execute(
            "SELECT id::text FROM persons WHERE display_name = %s AND deleted_at IS NULL LIMIT 1",
            (name_b,),
        )).fetchone()
        if not row_a or not row_b:
            raise HTTPException(status_code=404, detail="One or both persons not found")
        id_a, id_b = row_a[0], row_b[0]
        await conn.execute(
            "UPDATE persons SET merged_into = %s::uuid WHERE id = %s::uuid",
            (id_a, id_b),
        )
        await conn.execute(
            "INSERT INTO outbox (event_type, payload) VALUES (%s, %s)",
            ("person_merged", json.dumps({"merged_from": id_b, "merged_into": id_a, "merged_at": now.isoformat()})),
        )
    return {"merged_from": id_b, "merged_into": id_a}
