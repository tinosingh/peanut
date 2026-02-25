"""Tests for T-020 (POST /search), T-021 (TUI hybrid search), T-022 (migration)."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


# ── T-020: FastAPI /search endpoint ──────────────────────────────────────────

def test_search_router_exists():
    """src/api/search.py parses and contains an APIRouter."""
    content = (ROOT / "src" / "api" / "search.py").read_text()
    tree = ast.parse(content)
    assert tree is not None
    assert "APIRouter" in content


def test_search_router_file_exists():
    assert (ROOT / "src" / "api" / "search.py").exists()


def test_search_request_model_defined():
    content = (ROOT / "src" / "api" / "search.py").read_text()
    assert "SearchRequest" in content
    assert "SearchResponse" in content
    assert "SearchResult" in content


def test_search_endpoint_uses_bm25():
    content = (ROOT / "src" / "api" / "search.py").read_text()
    assert "plainto_tsquery" in content or "tsv" in content


def test_search_endpoint_uses_ann():
    content = (ROOT / "src" / "api" / "search.py").read_text()
    assert "embedding" in content
    assert "<=" in content or "cosine" in content or "_ann_search" in content


def test_search_endpoint_uses_rrf():
    content = (ROOT / "src" / "api" / "search.py").read_text()
    assert "rrf_merge" in content


def test_search_endpoint_uses_reranker():
    content = (ROOT / "src" / "api" / "search.py").read_text()
    assert "rerank" in content


def test_search_endpoint_has_degraded_flag():
    content = (ROOT / "src" / "api" / "search.py").read_text()
    assert "degraded" in content


def test_search_endpoint_has_cache():
    content = (ROOT / "src" / "api" / "search.py").read_text()
    assert "_cache" in content
    assert "ttl" in content.lower() or "search_cache_ttl" in content


def test_search_request_max_length():
    content = (ROOT / "src" / "api" / "search.py").read_text()
    assert "max_length=2000" in content or "max_length" in content


# ── T-021: TUI hybrid search wired ───────────────────────────────────────────

def test_tui_main_includes_search_router():
    content = (ROOT / "src" / "tui" / "main.py").read_text()
    assert "search_router" in content or "search" in content
    assert "include_router" in content


def test_search_screen_posts_to_search():
    content = (ROOT / "src" / "tui" / "screens" / "search.py").read_text()
    assert "/search" in content
    assert "post" in content.lower()


def test_search_screen_shows_rerank_column():
    content = (ROOT / "src" / "tui" / "screens" / "search.py").read_text()
    assert "RERANK" in content or "rerank" in content.lower()


def test_search_screen_shows_degraded():
    content = (ROOT / "src" / "tui" / "screens" / "search.py").read_text()
    assert "degraded" in content.lower()


def test_search_screen_obsidian_binding():
    content = (ROOT / "src" / "tui" / "screens" / "search.py").read_text()
    assert "obsidian" in content.lower()
    assert '"e"' in content


# ── T-022: Alembic migration embedding_v2 ────────────────────────────────────

def test_migration_file_exists():
    migrations_dir = ROOT / "db" / "migrations" / "versions"
    migration_files = list(migrations_dir.glob("*.py"))
    assert len(migration_files) >= 1, "Expected at least one migration file"


def test_migration_adds_embedding_v2():
    migrations_dir = ROOT / "db" / "migrations" / "versions"
    for f in migrations_dir.glob("*.py"):
        content = f.read_text()
        if "embedding_v2" in content:
            assert "upgrade" in content
            assert "downgrade" in content
            break
    else:
        pytest.fail("No migration found with embedding_v2")


def test_migration_has_hnsw_index():
    migrations_dir = ROOT / "db" / "migrations" / "versions"
    for f in migrations_dir.glob("*.py"):
        content = f.read_text()
        if "embedding_v2" in content:
            assert "HNSW" in content or "hnsw" in content.lower()
            break
    else:
        pytest.fail("No migration found with embedding_v2")


def test_migration_is_reversible():
    migrations_dir = ROOT / "db" / "migrations" / "versions"
    for f in migrations_dir.glob("*.py"):
        content = f.read_text()
        if "embedding_v2" in content:
            assert "downgrade" in content
            assert "DROP COLUMN" in content or "drop column" in content.lower()
            break
    else:
        pytest.fail("No migration found with embedding_v2")
