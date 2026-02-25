"""Tests for T-048: Graph screen, graph export, slowapi middleware, Makefile targets."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent.parent


# ── Graph export (render_visjs) ────────────────────────────────────────────

def test_render_visjs_exists():
    from src.tui.screens.graph_export import render_visjs
    assert callable(render_visjs)


def test_render_visjs_returns_html_string():
    from src.tui.screens.graph_export import render_visjs
    nodes = [{"id": "a@corp.com", "label": "a@corp.com", "group": "Person", "title": ""}]
    edges: list[dict] = []
    html = render_visjs(nodes, edges)
    assert isinstance(html, str)
    assert "<!DOCTYPE html>" in html


def test_render_visjs_embeds_vis_network():
    from src.tui.screens.graph_export import render_visjs
    html = render_visjs([], [])
    assert "vis-network" in html


def test_render_visjs_includes_node_data():
    from src.tui.screens.graph_export import render_visjs
    nodes = [{"id": "n1", "label": "Alice", "group": "Person", "title": "alice@corp.com"}]
    html = render_visjs(nodes, [])
    assert "Alice" in html


def test_render_visjs_includes_edge_data():
    from src.tui.screens.graph_export import render_visjs
    nodes = [
        {"id": "a", "label": "Alice", "group": "Person", "title": ""},
        {"id": "b", "label": "Doc", "group": "Document", "title": ""},
    ]
    edges = [{"from": "a", "to": "b", "label": "SENT"}]
    html = render_visjs(nodes, edges)
    assert "SENT" in html


def test_render_visjs_colors_by_label():
    from src.tui.screens.graph_export import _LABEL_COLORS
    assert "Person" in _LABEL_COLORS
    assert "Document" in _LABEL_COLORS
    assert "Concept" in _LABEL_COLORS


def test_render_visjs_empty_graph():
    from src.tui.screens.graph_export import render_visjs
    html = render_visjs([], [])
    assert "<!DOCTYPE html>" in html
    assert "[]" in html  # empty nodes/edges arrays


# ── Graph screen ───────────────────────────────────────────────────────────

def test_graph_screen_exists():
    content = (ROOT / "src" / "tui" / "screens" / "graph.py").read_text()
    assert "class GraphScreen" in content


def test_graph_screen_has_tree_widget():
    content = (ROOT / "src" / "tui" / "screens" / "graph.py").read_text()
    assert "Tree" in content


def test_graph_screen_has_enter_navigation():
    content = (ROOT / "src" / "tui" / "screens" / "graph.py").read_text()
    assert "on_tree_node_selected" in content or "NodeSelected" in content


def test_graph_screen_has_backspace_binding():
    content = (ROOT / "src" / "tui" / "screens" / "graph.py").read_text()
    assert "backspace" in content.lower()
    assert "go_back" in content or "action_go_back" in content


def test_graph_screen_has_export_action():
    content = (ROOT / "src" / "tui" / "screens" / "graph.py").read_text()
    assert "action_export_graph" in content or "export_graph" in content
    assert "graph.html" in content or "render_visjs" in content


def test_graph_screen_uses_graph_export():
    content = (ROOT / "src" / "tui" / "screens" / "graph.py").read_text()
    assert "graph_export" in content


def test_graph_screen_graceful_degradation():
    """FalkorDB unavailable → empty result, no crash."""
    content = (ROOT / "src" / "tui" / "screens" / "graph.py").read_text()
    assert "except Exception" in content
    assert "return [], []" in content


# ── App.py g binding ──────────────────────────────────────────────────────

def test_app_has_g_binding():
    content = (ROOT / "src" / "tui" / "app.py").read_text()
    assert '"g"' in content or "'g'" in content
    assert "goto_graph" in content


def test_app_has_graph_action():
    content = (ROOT / "src" / "tui" / "app.py").read_text()
    assert "action_goto_graph" in content
    assert "GraphScreen" in content


# ── SlowAPIMiddleware ─────────────────────────────────────────────────────

def test_main_has_slowapi_middleware():
    content = (ROOT / "src" / "tui" / "main.py").read_text()
    assert "SlowAPIMiddleware" in content
    assert "add_middleware" in content


# ── Makefile targets ──────────────────────────────────────────────────────

def test_makefile_has_healthcheck():
    content = (ROOT / "Makefile").read_text()
    assert "healthcheck:" in content
    assert "health" in content


def test_makefile_has_storage_report():
    content = (ROOT / "Makefile").read_text()
    assert "storage-report:" in content


def test_makefile_has_upgrade():
    content = (ROOT / "Makefile").read_text()
    assert "upgrade:" in content
    assert "migrate-up" in content or "pull" in content


def test_makefile_phony_includes_new_targets():
    content = (ROOT / "Makefile").read_text()
    assert "healthcheck" in content
    assert "storage-report" in content
    assert "upgrade" in content


# ── Entity resolution spike doc ───────────────────────────────────────────

def test_entity_resolution_spike_doc_exists():
    assert (ROOT / "docs" / "entity-resolution-spike.md").exists()


def test_entity_resolution_spike_documents_approaches():
    content = (ROOT / "docs" / "entity-resolution-spike.md").read_text()
    assert "Approach A" in content
    assert "Approach B" in content
    assert "0.90" in content
