"""Outbox worker — drains graph events from Postgres outbox to FalkorDB.

Guarantees: Postgres and FalkorDB converge even if FalkorDB was temporarily down.
After OUTBOX_MAX_ATTEMPTS failures, row.failed=True (dead-lettered).
Never written directly from ingest path — all graph writes go through here.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

log = structlog.get_logger()

OUTBOX_POLL_INTERVAL = 2
OUTBOX_BATCH_SIZE = 50
OUTBOX_MAX_ATTEMPTS = 10


def _apply_outbox_event(graph: Any, event_type: str, payload: dict) -> None:
    """Apply a single outbox event to FalkorDB."""
    if event_type == "document_added":
        sender = payload.get("sender", {})
        doc_id = payload["doc_id"]
        ingested_at = payload.get("ingested_at", "")

        # Sender :SENT edge
        graph.query(
            "MERGE (p:Person {email: $email}) "
            "ON CREATE SET p.id = $pid, p.display_name = $name, p.pii = true "
            "MERGE (d:Document {id: $doc_id}) "
            "ON CREATE SET d.source_path = $path, d.source_type = $type, d.ingested_at = $ts "
            "MERGE (p)-[r:SENT {thread_id: $doc_id}]->(d) "
            "ON CREATE SET r.valid_at = $ts",
            {
                "email": sender.get("email", "unknown@unknown"),
                "pid": sender.get("id", doc_id),
                "name": sender.get("name", ""),
                "doc_id": doc_id,
                "path": payload.get("source_path", ""),
                "type": payload.get("source_type", ""),
                "ts": ingested_at,
            },
        )

        # :RECEIVED edges for each recipient
        for r in payload.get("recipients", []):
            graph.query(
                "MERGE (p:Person {email: $email}) "
                "ON CREATE SET p.pii = true "
                "MERGE (d:Document {id: $doc_id}) "
                "MERGE (p)-[rel:RECEIVED {thread_id: $doc_id, field: $field}]->(d) "
                "ON CREATE SET rel.valid_at = $ts",
                {
                    "email": r["email"],
                    "doc_id": doc_id,
                    "field": r.get("field", "to"),
                    "ts": ingested_at,
                },
            )

    elif event_type == "entity_deleted":
        graph.query("MATCH (n {id: $id}) DETACH DELETE n", {"id": payload["id"]})

    elif event_type == "person_merged":
        graph.query(
            "MATCH (a:Person {id: $from_id})-[r]->() SET r.invalid_at = $ts",
            {"from_id": payload["from_id"], "ts": payload.get("ts", "")},
        )


async def outbox_worker(
    pool: Any,   # AsyncConnectionPool
    falkordb_host: str,
    falkordb_port: int,
) -> None:
    """Continuously drain outbox → FalkorDB."""
    from falkordb import FalkorDB
    db = FalkorDB(host=falkordb_host, port=falkordb_port)
    graph = db.select_graph("pkg")

    log.info("outbox_worker_started", host=falkordb_host, port=falkordb_port)
    while True:
        try:
            async with pool.connection() as conn:
                rows = await conn.execute("""
                    SELECT id, event_type, payload, attempts FROM outbox
                    WHERE processed_at IS NULL AND NOT failed
                    ORDER BY created_at
                    LIMIT %s
                """, (OUTBOX_BATCH_SIZE,)).fetchall()

            for row_id, event_type, payload_raw, attempts in rows:
                payload = payload_raw if isinstance(payload_raw, dict) else json.loads(payload_raw)

                if attempts >= OUTBOX_MAX_ATTEMPTS:
                    async with pool.connection() as conn:
                        await conn.execute("""
                            UPDATE outbox SET failed = true, error = 'max attempts exceeded'
                            WHERE id = %s
                        """, (row_id,))
                    log.warning("outbox_dead_lettered", row_id=row_id)
                    continue

                try:
                    _apply_outbox_event(graph, event_type, payload)
                    async with pool.connection() as conn:
                        await conn.execute("""
                            UPDATE outbox
                            SET processed_at = now(), attempts = attempts + 1
                            WHERE id = %s
                        """, (row_id,))

                except Exception as exc:
                    log.error("outbox_event_failed", row_id=row_id, error=str(exc))
                    async with pool.connection() as conn:
                        await conn.execute("""
                            UPDATE outbox SET error = %s, attempts = attempts + 1
                            WHERE id = %s
                        """, (str(exc), row_id))

        except Exception as exc:
            log.error("outbox_worker_error", error=str(exc))

        await asyncio.sleep(OUTBOX_POLL_INTERVAL)
