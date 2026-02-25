"""MCP server mounted at /mcp/ — tools: add_document, search_facts, search_nodes.

Uses the MCP Python SDK (mcp>=1.0) to expose a FastAPI-compatible SSE endpoint.
Mounted into the tui-controller FastAPI app via app.mount('/mcp/', mcp_app).

Tools:
  add_document(text, metadata)    — ingest raw text into the knowledge base
  search_facts(query)             — hybrid BM25+ANN search returning snippets
  search_nodes(label, property_filter) — graph node lookup by label + filter
"""
from __future__ import annotations

import os
from typing import Any

import structlog

log = structlog.get_logger()

_mcp_app = None


def get_mcp_app():
    """Return (lazily built) the MCP ASGI app. Returns None if SDK unavailable."""
    global _mcp_app
    if _mcp_app is not None:
        return _mcp_app
    try:
        from mcp.server import Server
        from mcp.server.fastapi import MCPApp
        from mcp.types import TextContent, Tool

        server = Server("pkg-knowledge-base")

        @server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="add_document",
                    description="Ingest raw text into the personal knowledge base.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "Document text to ingest"},
                            "metadata": {"type": "object", "description": "Optional metadata (source, sender, etc.)"},
                        },
                        "required": ["text"],
                    },
                ),
                Tool(
                    name="search_facts",
                    description="Hybrid BM25+vector search over the knowledge base. Returns ranked snippets.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "limit": {"type": "integer", "default": 5, "description": "Max results"},
                        },
                        "required": ["query"],
                    },
                ),
                Tool(
                    name="search_nodes",
                    description="Look up graph nodes by label and optional property filter.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "Node label (Person, Concept, etc.)"},
                            "property_filter": {"type": "object", "description": "Key-value property filters"},
                        },
                        "required": ["label"],
                    },
                ),
            ]

        @server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            import httpx
            api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
            async with httpx.AsyncClient(timeout=30) as client:
                if name == "add_document":
                    resp = await client.post(
                        f"{api_url}/ingest/text",
                        json={"text": arguments["text"], "metadata": arguments.get("metadata", {})},
                    )
                    resp.raise_for_status()
                    return [TextContent(type="text", text=f"Ingested: {resp.json()}")]

                elif name == "search_facts":
                    resp = await client.post(
                        f"{api_url}/search",
                        json={"q": arguments["query"], "limit": arguments.get("limit", 5)},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    snippets = "\n\n".join(
                        f"[{i+1}] {r['snippet']} (source: {r['source_path']})"
                        for i, r in enumerate(data.get("results", []))
                    )
                    degraded = " [DEGRADED — BM25 only]" if data.get("degraded") else ""
                    return [TextContent(type="text", text=snippets + degraded)]

                elif name == "search_nodes":
                    resp = await client.get(
                        f"{api_url}/graph/nodes",
                        params={
                            "label": arguments["label"],
                            **{f"filter_{k}": v for k, v in arguments.get("property_filter", {}).items()},
                        },
                    )
                    resp.raise_for_status()
                    nodes = resp.json().get("nodes", [])
                    return [TextContent(type="text", text=str(nodes))]

                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]

        _mcp_app = MCPApp(server)
        log.info("mcp_server_ready")
        return _mcp_app

    except ImportError as exc:
        log.warning("mcp_sdk_unavailable", error=str(exc))
        return None
    except Exception as exc:
        log.error("mcp_server_init_failed", error=str(exc))
        return None
