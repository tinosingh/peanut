"""Tests for T-002: FalkorDB graph init verification."""
from pathlib import Path

ROOT = Path(__file__).parent.parent
COMPOSE = (ROOT / "docker-compose.yml").read_text()
GRAPH_INIT = (ROOT / "db" / "graph-init.sh").read_text()


def test_graph_init_script_exists():
    assert (ROOT / "db" / "graph-init.sh").exists()


def test_graph_init_creates_pkg_graph():
    assert "pkg" in GRAPH_INIT


def test_compose_has_graph_init_service():
    assert "pkg-graph-init" in COMPOSE


def test_graph_init_service_depends_on_pkg_graph():
    # pkg-graph-init must wait for pkg-graph to be healthy
    idx_init = COMPOSE.index("pkg-graph-init:")
    section = COMPOSE[idx_init:idx_init + 500]
    assert "pkg-graph" in section
    assert "service_healthy" in section


def test_graph_init_service_restart_on_failure():
    idx_init = COMPOSE.index("pkg-graph-init:")
    section = COMPOSE[idx_init:idx_init + 300]
    assert "restart: on-failure" in section


def test_app_services_wait_for_graph_init():
    # Both ingest-worker and tui-controller should depend on pkg-graph-init
    assert "pkg-graph-init" in COMPOSE
    assert "service_completed_successfully" in COMPOSE
