"""Prometheus metrics endpoint — mounted at /metrics (T-045).

Metrics exposed:
  pkg_chunks_total           — total chunks by embedding_status
  pkg_ingest_latency_seconds — histogram (populated by ingest worker)
  pkg_query_latency_seconds  — histogram (populated by /search endpoint)
  pkg_outbox_depth           — current unprocessed outbox depth

Graceful degradation: if prometheus_client not installed, returns 503.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Response

log = structlog.get_logger()

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus text format metrics."""
    try:
        import prometheus_client  # noqa: F401 — verify SDK available

        from src.shared.db import get_pool

        pool = await get_pool()
        async with pool.connection() as conn:
            # Chunk embedding status
            rows = await (await conn.execute(
                "SELECT embedding_status, COUNT(*) FROM chunks GROUP BY embedding_status"
            )).fetchall()

            # Outbox total depth
            outbox_row = await (await conn.execute(
                "SELECT COUNT(*) FROM outbox WHERE processed_at IS NULL AND NOT failed"
            )).fetchone()

            # Outbox depth by event type
            outbox_by_type = await (await conn.execute(
                "SELECT event_type, COUNT(*) FROM outbox WHERE processed_at IS NULL AND NOT failed GROUP BY event_type"
            )).fetchall()

            # Oldest pending event age (seconds)
            outbox_oldest = await (await conn.execute(
                "SELECT EXTRACT(EPOCH FROM (NOW() - MIN(created_at))) FROM outbox WHERE processed_at IS NULL AND NOT failed"
            )).fetchone()

        # Build metric output manually to avoid global state issues in tests
        lines = ["# HELP pkg_chunks_total Total chunks by embedding status",
                 "# TYPE pkg_chunks_total gauge"]
        for status, count in rows:
            lines.append(f'pkg_chunks_total{{status="{status}"}} {count}')

        outbox_depth = outbox_row[0] if outbox_row else 0
        lines.append("# HELP pkg_outbox_depth Current unprocessed outbox depth")
        lines.append("# TYPE pkg_outbox_depth gauge")
        lines.append(f"pkg_outbox_depth {outbox_depth}")

        # Per-event-type pending counts
        lines.append("# HELP pkg_outbox_pending_events Pending outbox events by type")
        lines.append("# TYPE pkg_outbox_pending_events gauge")
        for event_type, count in outbox_by_type:
            lines.append(f'pkg_outbox_pending_events{{event_type="{event_type}"}} {count}')

        # Oldest pending event age
        oldest_age = outbox_oldest[0] if outbox_oldest and outbox_oldest[0] is not None else 0
        lines.append("# HELP pkg_outbox_oldest_pending_seconds Age of oldest pending event")
        lines.append("# TYPE pkg_outbox_oldest_pending_seconds gauge")
        lines.append(f"pkg_outbox_oldest_pending_seconds {oldest_age}")

        body = "\n".join(lines) + "\n"
        return Response(content=body, media_type="text/plain; version=0.0.4")

    except ImportError:
        log.warning("prometheus_client_unavailable")
        return Response(
            content="# prometheus_client not installed\n",
            status_code=503,
            media_type="text/plain",
        )
    except Exception as exc:
        log.error("metrics_failed", error=str(exc))
        return Response(
            content=f"# error: {type(exc).__name__}\n",
            status_code=500, media_type="text/plain",
        )
