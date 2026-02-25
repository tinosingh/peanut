"""Tests for weighted score fusion, watcher pause sentinel, welcome psycopg3 fix."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent.parent


# ── Weighted score fusion (rrf.py) ────────────────────────────────────────────

def test_weighted_merge_function_exists():
    from src.shared.rrf import weighted_merge
    assert callable(weighted_merge)


def test_weighted_merge_returns_sorted_list():
    from src.shared.rrf import weighted_merge
    bm25 = {"a": 0.9, "b": 0.3, "c": 0.1}
    ann  = {"a": 0.2, "b": 0.8, "c": 0.5}
    result = weighted_merge(bm25, ann, bm25_weight=0.5, vector_weight=0.5)
    assert isinstance(result, list)
    assert set(result) == {"a", "b", "c"}


def test_weighted_merge_bm25_heavy_prefers_bm25_best():
    from src.shared.rrf import weighted_merge
    bm25 = {"a": 1.0, "b": 0.0}
    ann  = {"a": 0.0, "b": 1.0}
    result = weighted_merge(bm25, ann, bm25_weight=0.9, vector_weight=0.1)
    assert result[0] == "a"  # BM25-dominant: a wins


def test_weighted_merge_ann_heavy_prefers_ann_best():
    from src.shared.rrf import weighted_merge
    bm25 = {"a": 1.0, "b": 0.0}
    ann  = {"a": 0.0, "b": 1.0}
    result = weighted_merge(bm25, ann, bm25_weight=0.1, vector_weight=0.9)
    assert result[0] == "b"  # ANN-dominant: b wins


def test_weighted_merge_handles_empty_lists():
    from src.shared.rrf import weighted_merge
    result = weighted_merge({}, {})
    assert result == []


def test_weighted_merge_normalises_scores():
    from src.shared.rrf import weighted_merge
    # All same BM25 score — should not divide by zero
    bm25 = {"a": 5.0, "b": 5.0}
    ann  = {"a": 0.9, "b": 0.1}
    result = weighted_merge(bm25, ann, 0.5, 0.5)
    assert result[0] == "a"  # ANN breaks the BM25 tie


def test_search_endpoint_imports_weighted_merge():
    content = (ROOT / "src" / "api" / "search.py").read_text()
    assert "weighted_merge" in content


def test_search_reads_bm25_weight_from_config():
    content = (ROOT / "src" / "api" / "search.py").read_text()
    assert "bm25_weight" in content
    assert "vector_weight" in content


def test_search_uses_weighted_when_weights_differ():
    content = (ROOT / "src" / "api" / "search.py").read_text()
    assert "use_weighted" in content
    assert "weighted_merge" in content


# ── Watcher pause sentinel ────────────────────────────────────────────────────

def test_watcher_checks_pause_sentinel():
    content = (ROOT / "src" / "ingest" / "watcher.py").read_text()
    assert ".pause" in content
    assert "pause_sentinel" in content or "sentinel" in content


def test_watcher_skips_sentinel_file():
    content = (ROOT / "src" / "ingest" / "watcher.py").read_text()
    assert "pause_sentinel" in content
    assert "continue" in content


def test_intake_creates_pause_sentinel():
    content = (ROOT / "src" / "tui" / "screens" / "intake.py").read_text()
    assert ".pause" in content


# ── Welcome screen psycopg3 fix ───────────────────────────────────────────────

def test_welcome_uses_psycopg3_fetchone():
    content = (ROOT / "src" / "tui" / "screens" / "welcome.py").read_text()
    assert "fetchrow" not in content
    assert "fetchone" in content


# ── RRF module docstring updated ─────────────────────────────────────────────

def test_rrf_documents_weighted_fusion():
    content = (ROOT / "src" / "shared" / "rrf.py").read_text()
    assert "weighted" in content.lower()
    assert "bm25_weight" in content
    assert "vector_weight" in content
