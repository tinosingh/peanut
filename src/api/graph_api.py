"""GET /graph/nodes — look up FalkorDB nodes by label and property filter.

Used by the MCP search_nodes tool. Supports arbitrary label and key=value
property filters passed as query params prefixed with filter_.

Example:
    GET /graph/nodes?label=Person&filter_email=alice%40example.com
"""
from __future__ import annotations

import os
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request

log = structlog.get_logger()

router = APIRouter()

_LABEL_ALLOWLIST = {"Person", "Document", "Concept", "Chunk"}
_MAX_RESULTS = 50


@router.get("/graph/nodes")
async def graph_nodes(request: Request, label: str) -> dict[str, Any]:
    """Return graph nodes matching label + optional property filters."""
    if label not in _LABEL_ALLOWLIST:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown label '{label}'. Allowed: {sorted(_LABEL_ALLOWLIST)}",
        )

    # Collect filter_* query params → property filters
    filters: dict[str, str] = {}
    for key, val in request.query_params.items():
        if key.startswith("filter_"):
            prop = key[len("filter_"):]
            if prop and len(prop) <= 64 and len(val) <= 1000:
                filters[prop] = val

    # Build Cypher using named parameters (no string interpolation on values)
    where_clause = ""
    cypher_params: dict[str, str] = {}
    if filters:
        conditions = []
        for prop, val in filters.items():
            safe_prop = prop.replace("`", "")  # strip backtick injection
            param_name = f"p_{safe_prop}"
            conditions.append(f"n.`{safe_prop}` = ${param_name}")
            cypher_params[param_name] = val
        where_clause = " WHERE " + " AND ".join(conditions)

    cypher = f"MATCH (n:{label}){where_clause} RETURN n LIMIT {_MAX_RESULTS}"

    try:
        from falkordb import FalkorDB

        host = os.getenv("FALKORDB_HOST", "pkg-graph")
        port = int(os.getenv("FALKORDB_PORT", "6379"))
        db = FalkorDB(host=host, port=port)
        graph = db.select_graph("pkg")
        result = graph.query(cypher, cypher_params)
        nodes = [dict(row[0].properties) for row in result.result_set]
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="FalkorDB SDK not available") from exc
    except Exception as exc:
        log.error("graph_nodes_query_failed", label=label, error=str(exc))
        raise HTTPException(status_code=503, detail="Graph query failed") from exc

    log.info("graph_nodes_queried", label=label, filters=list(filters.keys()), count=len(nodes))
    return {"nodes": nodes, "label": label, "count": len(nodes)}
