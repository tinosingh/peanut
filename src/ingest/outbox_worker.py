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

# Circuit breaker: pause processing if FalkorDB fails repeatedly
_FALKORDB_ERROR_THRESHOLD = 5
_CIRCUIT_BREAKER_BACKOFF = 60  # seconds


def _apply_outbox_event(graph: Any, event_type: str, payload: dict) -> None:
    """Apply a single outbox event to FalkorDB.

    Uses MERGE (idempotent) queries so replayed events don't create duplicates.
    """
    if event_type == "document_added":
        sender = payload.get("sender", {})
        doc_id = payload["doc_id"]
        ingested_at = payload.get("ingested_at", "")

        # Build a single batched Cypher query for sender + all recipients
        source_path = payload.get("source_path", "")
        # Extract filename for graph display (e.g., "/drop-zone/foo.pdf" → "foo.pdf")
        doc_title = source_path.split("/")[-1] if source_path else "Document"

        cypher_parts = [
            "MERGE (sender:Person {email: $sender_email}) "
            "ON CREATE SET sender.id = $pid, sender.display_name = $name, sender.pii = true "
            "MERGE (d:Document {id: $doc_id}) "
            "ON CREATE SET d.source_path = $path, d.source_type = $type, d.title = $title, d.ingested_at = $ts "
            "MERGE (sender)-[sr:SENT {thread_id: $doc_id}]->(d) "
            "ON CREATE SET sr.valid_at = $ts"
        ]
        params: dict[str, str] = {
            "sender_email": sender.get("email", "unknown@unknown"),
            "pid": sender.get("id", doc_id),
            "name": sender.get("name", ""),
            "doc_id": doc_id,
            "path": source_path,
            "title": doc_title,
            "type": payload.get("source_type", ""),
            "ts": ingested_at,
        }

        for i, r in enumerate(payload.get("recipients", [])):
            alias = f"r{i}"
            email_key = f"remail_{i}"
            field_key = f"rfield_{i}"
            cypher_parts.append(
                f"MERGE ({alias}:Person {{email: ${email_key}}}) "
                f"ON CREATE SET {alias}.pii = true "
                f"MERGE ({alias})-[rel{i}:RECEIVED {{thread_id: $doc_id, field: ${field_key}}}]->(d) "
                f"ON CREATE SET rel{i}.valid_at = $ts"
            )
            params[email_key] = r["email"]
            params[field_key] = r.get("field", "to")

        cypher = " ".join(cypher_parts)
        graph.query(cypher, params)

    elif event_type == "entity_deleted":
        # Handle both old and new field names for backwards compatibility
        entity_id = payload.get("entity_id") or payload.get("id")
        if entity_id:
            graph.query("MATCH (n {id: $id}) DETACH DELETE n", {"id": entity_id})
        else:
            log.warning("entity_deleted_missing_id", payload=payload)

    elif event_type == "person_merged":
        # Handle both old and new field names for backwards compatibility
        from_id = payload.get("merged_from") or payload.get("from_id")
        if from_id:
            ts = payload.get("merged_at") or payload.get("ts", "")
            graph.query(
                "MATCH (a:Person {id: $from_id})-[r]->() SET r.invalid_at = $ts",
                {"from_id": from_id, "ts": ts},
            )
        else:
            log.warning("person_merged_missing_from_id", payload=payload)


async def outbox_worker(
    pool: Any,   # AsyncConnectionPool
    falkordb_host: str,
    falkordb_port: int,
) -> None:
    """Continuously drain outbox → FalkorDB."""
    from falkordb import FalkorDB

    # Retry FalkorDB connection with exponential backoff
    graph = None
    for attempt in range(10):
        try:
            db = FalkorDB(host=falkordb_host, port=falkordb_port)
            graph = db.select_graph("pkg")
            break
        except Exception as exc:
            delay = min(2 ** attempt, 60)
            log.warning("falkordb_connect_retry",
                attempt=attempt + 1, delay=delay, error=str(exc))
            await asyncio.sleep(delay)
    if graph is None:
        log.error("falkordb_connect_failed", host=falkordb_host, port=falkordb_port)
        return

    log.info("outbox_worker_started", host=falkordb_host, port=falkordb_port)
    falkordb_consecutive_errors = 0
    while True:
        try:
            async with pool.connection() as conn:
                rows = await (await conn.execute("""
                    SELECT id, event_type, payload, attempts FROM outbox
                    WHERE processed_at IS NULL AND NOT failed
                    ORDER BY created_at
                    LIMIT %s
                """, (OUTBOX_BATCH_SIZE,))).fetchall()

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
                    import time

                    # Mark processed BEFORE graph write — idempotent replay is
                    # safer than duplicate edges from replaying on crash.
                    async with pool.connection() as conn:
                        await conn.execute("""
                            UPDATE outbox
                            SET processed_at = now(), attempts = attempts + 1
                            WHERE id = %s AND processed_at IS NULL
                        """, (row_id,))

                    start = time.time()
                    _apply_outbox_event(graph, event_type, payload)
                    latency_ms = (time.time() - start) * 1000

                    log.info("outbox_event_processed",
                        row_id=row_id,
                        event_type=event_type,
                        latency_ms=latency_ms,
                        payload_size=len(str(payload)))
                    falkordb_consecutive_errors = 0  # reset on success

                except Exception as exc:
                    falkordb_consecutive_errors += 1
                    log.error("outbox_event_failed",
                        row_id=row_id,
                        event_type=event_type,
                        error=str(exc),
                        error_type=type(exc).__name__,
                        consecutive_errors=falkordb_consecutive_errors)
                    # Roll back: clear processed_at so event retries
                    async with pool.connection() as conn:
                        await conn.execute("""
                            UPDATE outbox
                            SET processed_at = NULL, error = %s, attempts = attempts + 1
                            WHERE id = %s
                        """, (str(exc), row_id))
                    if falkordb_consecutive_errors >= _FALKORDB_ERROR_THRESHOLD:
                        log.warning("outbox_circuit_breaker_open",
                            consecutive_errors=falkordb_consecutive_errors,
                            backoff_s=_CIRCUIT_BREAKER_BACKOFF)
                        await asyncio.sleep(_CIRCUIT_BREAKER_BACKOFF)
                        falkordb_consecutive_errors = 0

        except Exception as exc:
            log.error("outbox_worker_error", error=str(exc))

        await asyncio.sleep(OUTBOX_POLL_INTERVAL)
