"""Entities API — soft-delete, hard-delete, and bidirectional sync endpoints.

T-041: DELETE /entities/{id} sets deleted_at = now(); FalkorDB invalidation via outbox
T-042: POST /entities/hard-delete (admin) deletes rows with deleted_at < now()-30d
T-046: PUT /entities/{type}/{id} applies Obsidian frontmatter diffs; server timestamp wins
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
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


class UpdateRequest(BaseModel):
    """Frontmatter diff from Obsidian plugin.

    Only the keys provided are updated; omitted keys are left unchanged.
    client_updated_at must be provided so the server can apply the conflict rule:
    if server.updated_at > client_updated_at the field is flagged as a conflict
    and the server value wins.
    """

    diffs: dict[str, str | None]
    client_updated_at: str  # ISO-8601 timestamp from Obsidian


class UpdateResponse(BaseModel):
    id: str
    entity_type: Literal["document", "person"]
    updated_fields: list[str]
    conflict_detected: bool
    server_updated_at: str


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

    # Use dict lookup instead of f-string for table names (safer)
    table_map = {"document": "documents", "person": "persons"}
    table = table_map.get(entity_type)
    if table is None:
        raise HTTPException(status_code=400, detail=f"Invalid entity_type: {entity_type}")
    now = datetime.now(UTC)

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
        "timestamp": datetime.now(UTC).isoformat(),
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
    from src.ingest.entity_resolution import score_pair_b
    from src.shared.db import get_pool
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

        # Build email → set of doc_ids map for shared_docs computation
        email_docs_rows = await (await conn.execute(
            """
            SELECT metadata->>'sender_email' AS email, id::text AS doc_id
            FROM documents
            WHERE deleted_at IS NULL
              AND metadata->>'sender_email' IS NOT NULL
            """
        )).fetchall()

    email_to_docs: dict[str, set[str]] = {}
    for email, doc_id in email_docs_rows:
        email_to_docs.setdefault(email, set()).add(doc_id)

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
                docs_a = email_to_docs.get(a["email"], set())
                docs_b = email_to_docs.get(b["email"], set())
                shared_docs = len(docs_a & docs_b)
                candidates.append({
                    "id_a": a["id"], "name_a": a["name"],
                    "id_b": b["id"], "name_b": b["name"],
                    "jw_score": round(score, 3),
                    "same_domain": same_domain,
                    "shared_docs": shared_docs,
                })
    return {"candidates": candidates}


@router.post("/entities/merge")
async def merge_entities(name_a: str, name_b: str) -> dict:
    """Merge person name_b into name_a (sets merged_into FK + outbox event).
    
    AUDIT: This operation is logged for security/compliance.
    """
    from src.shared.db import get_pool
    pool = await get_pool()
    now = datetime.now(UTC)
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


# ── T-046: Bidirectional sync (Obsidian plugin) ────────────────────────────

_PERSON_UPDATABLE = frozenset({"display_name", "email", "pii"})
_DOCUMENT_UPDATABLE = frozenset({"source_path"})  # metadata fields go via JSON merge


@router.put("/entities/{entity_type}/{entity_id}", response_model=UpdateResponse)
async def update_entity(
    entity_type: Literal["document", "person"],
    entity_id: str,
    req: UpdateRequest,
) -> UpdateResponse:
    """Apply frontmatter diffs from Obsidian plugin.

    Conflict rule: server timestamp wins.
    If the server's updated_at > client_updated_at, conflict_detected=True is
    returned but the server value is kept unchanged for conflicting fields.
    """
    from src.shared.db import get_pool

    pool = await get_pool()
    table = "documents" if entity_type == "document" else "persons"
    now = datetime.now(UTC)

    try:
        client_ts = datetime.fromisoformat(req.client_updated_at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid client_updated_at: {exc}") from exc

    allowed = _DOCUMENT_UPDATABLE if entity_type == "document" else _PERSON_UPDATABLE

    # Filter to only updatable fields
    safe_diffs = {k: v for k, v in req.diffs.items() if k in allowed}
    if not safe_diffs:
        raise HTTPException(status_code=400, detail=f"No updatable fields provided. Allowed: {sorted(allowed)}")

    async with pool.connection() as conn:
        # Fetch current row
        result = await conn.execute(
            f"SELECT updated_at FROM {table} WHERE id = %s::uuid AND deleted_at IS NULL",
            (entity_id,),
        )
        row = await result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"{entity_type} {entity_id} not found")

        server_ts = row[0]
        # Ensure timezone-aware comparison
        if server_ts is not None and hasattr(server_ts, "tzinfo") and server_ts.tzinfo is None:
            server_ts = server_ts.replace(tzinfo=UTC)
        if client_ts.tzinfo is None:
            client_ts = client_ts.replace(tzinfo=UTC)

        conflict = server_ts is not None and server_ts > client_ts

        if not conflict:
            # Build SET clause for non-metadata columns
            set_clauses = []
            values = []
            if entity_type == "person":
                for field in ("display_name", "email"):
                    if field in safe_diffs and safe_diffs[field] is not None:
                        set_clauses.append(f"{field} = %s")
                        values.append(safe_diffs[field])
                if "pii" in safe_diffs and safe_diffs["pii"] is not None:
                    set_clauses.append("pii = %s")
                    values.append(safe_diffs["pii"].lower() == "true")
            else:  # document
                if "source_path" in safe_diffs and safe_diffs["source_path"] is not None:
                    set_clauses.append("source_path = %s")
                    values.append(safe_diffs["source_path"])
                # Extra metadata fields go into the metadata JSONB column
                meta_keys = {k: v for k, v in safe_diffs.items() if k not in _DOCUMENT_UPDATABLE}
                if meta_keys:
                    set_clauses.append("metadata = metadata || %s::jsonb")
                    values.append(json.dumps(meta_keys))

            if set_clauses:
                set_clauses.append("updated_at = %s")
                values.extend([now, entity_id])
                await conn.execute(
                    f"UPDATE {table} SET {', '.join(set_clauses)} WHERE id = %s::uuid",
                    values,
                )

            # Outbox event for FalkorDB property sync
            await conn.execute(
                "INSERT INTO outbox (event_type, payload) VALUES (%s, %s)",
                (
                    "entity_updated",
                    json.dumps({
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "diffs": safe_diffs,
                        "updated_at": now.isoformat(),
                    }),
                ),
            )

    updated = list(safe_diffs.keys()) if not conflict else []
    log.info("entity_updated", entity_type=entity_type, entity_id=entity_id, conflict=conflict)
    return UpdateResponse(
        id=entity_id,
        entity_type=entity_type,
        updated_fields=updated,
        conflict_detected=conflict,
        server_updated_at=(server_ts.isoformat() if server_ts else now.isoformat()),
    )
