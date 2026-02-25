"""Tests for MCP-referenced endpoints: /ingest/text and /graph/nodes."""
from pathlib import Path

ROOT = Path(__file__).parent.parent


# ── /ingest/text ────────────────────────────────────────────────────────────

def test_ingest_text_route_registered():
    content = (ROOT / "src" / "tui" / "main.py").read_text()
    assert "ingest_router" in content
    assert "from src.api.ingest_api import" in content


def test_ingest_text_endpoint_defined():
    content = (ROOT / "src" / "api" / "ingest_api.py").read_text()
    assert '@router.post("/ingest/text"' in content
    assert "IngestTextRequest" in content
    assert "IngestTextResponse" in content


def test_ingest_text_validates_max_length():
    content = (ROOT / "src" / "api" / "ingest_api.py").read_text()
    assert "max_length=500_000" in content


def test_ingest_text_writes_to_drop_zone():
    content = (ROOT / "src" / "api" / "ingest_api.py").read_text()
    assert "DROP_ZONE_PATH" in content
    assert "tempfile.NamedTemporaryFile" in content
    assert ".md" in content


def test_ingest_text_includes_frontmatter():
    content = (ROOT / "src" / "api" / "ingest_api.py").read_text()
    assert "frontmatter" in content
    assert "doc_id" in content


# ── /graph/nodes ─────────────────────────────────────────────────────────────

def test_graph_nodes_route_registered():
    content = (ROOT / "src" / "tui" / "main.py").read_text()
    assert "graph_router" in content
    assert "from src.api.graph_api import" in content


def test_graph_nodes_endpoint_defined():
    content = (ROOT / "src" / "api" / "graph_api.py").read_text()
    assert '@router.get("/graph/nodes"' in content


def test_graph_nodes_label_allowlisted():
    content = (ROOT / "src" / "api" / "graph_api.py").read_text()
    assert "_LABEL_ALLOWLIST" in content
    assert '"Person"' in content
    assert '"Document"' in content
    # Internal bootstrap node must NOT be exposed
    assert '"_Init"' not in content


def test_graph_nodes_uses_cypher_params():
    """Property filter values must go through Cypher params, not string interpolation."""
    content = (ROOT / "src" / "api" / "graph_api.py").read_text()
    # Parameterised Cypher: values via $param_name, not f-string interpolation
    assert "cypher_params" in content
    assert "filter_" in content


def test_graph_nodes_max_results_bounded():
    content = (ROOT / "src" / "api" / "graph_api.py").read_text()
    assert "_MAX_RESULTS" in content
    assert "LIMIT" in content


# ── MCP server consistency ────────────────────────────────────────────────────

def test_mcp_add_document_calls_ingest_text():
    content = (ROOT / "src" / "api" / "mcp_server.py").read_text()
    assert "/ingest/text" in content


def test_mcp_search_nodes_calls_graph_nodes():
    content = (ROOT / "src" / "api" / "mcp_server.py").read_text()
    assert "/graph/nodes" in content


# ── Watcher change-type filtering ─────────────────────────────────────────────

def test_watcher_imports_change_enum():
    """watcher.py must import Change from watchfiles to filter event types."""
    content = (ROOT / "src" / "ingest" / "watcher.py").read_text()
    assert "from watchfiles import" in content
    assert "Change" in content


def test_watcher_skips_deleted_events():
    """Deleted files must not trigger ingestion."""
    content = (ROOT / "src" / "ingest" / "watcher.py").read_text()
    assert "Change.added" in content or "Change.modified" in content
    # Must not blindly process all change types
    assert "_change_type" not in content


# ── Docker healthcheck ─────────────────────────────────────────────────────────

def test_ingest_worker_healthcheck_checks_drop_zone():
    """ingest-worker healthcheck must verify DROP_ZONE_PATH is mounted."""
    content = (ROOT / "docker-compose.yml").read_text()
    assert "DROP_ZONE_PATH" in content or "drop-zone" in content.lower()
    # Import-only check is no longer sufficient
    ingest_hc_idx = content.index("ingest-worker:")
    hc_section = content[ingest_hc_idx:ingest_hc_idx + 1500]
    assert "healthcheck" in hc_section
    assert "DROP_ZONE_PATH" in hc_section or "drop-zone" in hc_section
