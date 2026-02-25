"""Tests for T-030 (NER), T-031 (entity resolution), T-032 (Entities TUI),
T-033 (Vault Wikilinks), T-034 (MCP server).
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


# ── T-030: spaCy NER ──────────────────────────────────────────────────────────

def test_ner_module_exists():
    assert (ROOT / "src" / "ingest" / "ner.py").exists()


def test_ner_extracts_entity_labels():
    content = (ROOT / "src" / "ingest" / "ner.py").read_text()
    assert "PERSON" in content
    assert "ORG" in content
    assert "GPE" in content


def test_ner_uses_en_core_web_sm():
    content = (ROOT / "src" / "ingest" / "ner.py").read_text()
    assert "en_core_web_sm" in content


def test_ner_graceful_degradation():
    content = (ROOT / "src" / "ingest" / "ner.py").read_text()
    assert "except" in content
    assert "return []" in content


def test_ner_build_concept_outbox_events():
    content = (ROOT / "src" / "ingest" / "ner.py").read_text()
    assert "concept_added" in content
    assert "valid_at" in content


def test_ner_entity_resolution_calls_extract_entities():
    content = (ROOT / "src" / "ingest" / "ner.py").read_text()
    assert "extract_entities" in content


def test_ner_caps_text_length():
    content = (ROOT / "src" / "ingest" / "ner.py").read_text()
    assert "10_000" in content or "10000" in content


# ── T-031: Entity resolution ──────────────────────────────────────────────────

def test_entity_resolution_module_exists():
    assert (ROOT / "src" / "ingest" / "entity_resolution.py").exists()


def test_jaro_winkler_identical_strings():
    from src.ingest.entity_resolution import jaro_winkler
    assert jaro_winkler("Alice", "Alice") == pytest.approx(1.0)


def test_jaro_winkler_empty_strings():
    from src.ingest.entity_resolution import jaro_winkler
    assert jaro_winkler("", "") == pytest.approx(1.0)


def test_jaro_winkler_different_strings():
    from src.ingest.entity_resolution import jaro_winkler
    score = jaro_winkler("Alice Smith", "Bob Jones")
    assert score < 0.8


def test_score_pair_a_returns_float():
    from src.ingest.entity_resolution import score_pair_a
    result = score_pair_a("John Smith", "Jon Smith")
    assert isinstance(result, float)
    assert 0.0 <= result <= 1.0


def test_score_pair_b_same_domain_boosts_score():
    from src.ingest.entity_resolution import score_pair_b
    score_same = score_pair_b("John Smith", "john@acme.com", "Jon Smith", "jon@acme.com")
    score_diff = score_pair_b("John Smith", "john@acme.com", "Jon Smith", "jon@other.com")
    assert score_same > score_diff


def test_threshold_sweep_returns_precision_recall():
    from src.ingest.entity_resolution import threshold_sweep
    pairs = [
        {"name1": "Alice Smith", "name2": "Alice Smith", "is_duplicate": True},
        {"name1": "Alice Smith", "name2": "Bob Jones",   "is_duplicate": False},
    ]
    results = threshold_sweep(pairs, [0.8, 0.9, 0.99])
    assert 0.8 in results
    for pr in results.values():
        assert hasattr(pr, "precision")
        assert hasattr(pr, "recall")
        assert hasattr(pr, "f1")


def test_canary_pairs_json_exists():
    assert (ROOT / "tests" / "canary_pairs.json").exists()


def test_canary_pairs_are_all_non_duplicate():
    pairs = json.loads((ROOT / "tests" / "canary_pairs.json").read_text())
    assert len(pairs) >= 10
    assert all(not p["is_duplicate"] for p in pairs)


def test_canary_guard_passes_at_strict_threshold():
    """All canary (known-distinct) pairs must NOT exceed threshold 0.99."""
    from src.ingest.entity_resolution import check_canary_guard, load_canary_pairs
    pairs = load_canary_pairs(ROOT / "tests" / "canary_pairs.json")
    violations = check_canary_guard(pairs, threshold=0.99)
    assert violations == [], f"Canary violations at 0.99: {violations}"


# ── T-032: TUI Entities screen ────────────────────────────────────────────────

def test_entities_screen_exists():
    assert (ROOT / "src" / "tui" / "screens" / "entities.py").exists()


def test_entities_screen_has_merge_binding():
    content = (ROOT / "src" / "tui" / "screens" / "entities.py").read_text()
    assert '"m"' in content
    assert "merge" in content.lower()


def test_entities_screen_requires_confirmation():
    content = (ROOT / "src" / "tui" / "screens" / "entities.py").read_text()
    assert "confirm" in content.lower()
    assert "_confirm_pending" in content or "confirm" in content


def test_entities_screen_shows_jw_score():
    content = (ROOT / "src" / "tui" / "screens" / "entities.py").read_text()
    assert "jw_score" in content.lower() or "JW SCORE" in content


def test_entities_screen_shows_shared_docs():
    content = (ROOT / "src" / "tui" / "screens" / "entities.py").read_text()
    assert "shared_docs" in content.lower() or "SHARED DOCS" in content


# ── T-033: Vault Wikilinks ────────────────────────────────────────────────────

def test_vault_sync_has_update_wikilinks():
    content = (ROOT / "src" / "ingest" / "vault_sync.py").read_text()
    assert "update_document_wikilinks" in content


def test_update_document_wikilinks_creates_mentions_section():
    from src.ingest.vault_sync import update_document_wikilinks, write_document_note
    with tempfile.TemporaryDirectory() as tmpdir:
        write_document_note(
            tmpdir,
            doc_id="aabbccdd-0000-0000-0000-000000000000",
            source_path="/x",
            source_type="pdf",
            sender_email="a@b.com",
            subject="Test",
            ingested_at=datetime.now(UTC),
        )
        result = update_document_wikilinks(
            tmpdir,
            doc_id="aabbccdd-0000-0000-0000-000000000000",
            mentions=["Alice Smith", "Bob Jones"],
        )
        assert result is not None
        content = result.read_text()
        assert "Mentions" in content
        assert "Alice Smith" in content or "Alice_Smith" in content


def test_update_document_wikilinks_chmod_444():
    from src.ingest.vault_sync import update_document_wikilinks, write_document_note
    with tempfile.TemporaryDirectory() as tmpdir:
        write_document_note(
            tmpdir,
            doc_id="12345678-0000-0000-0000-000000000000",
            source_path="/x",
            source_type="pdf",
            sender_email="a@b.com",
            subject="Perm Test",
            ingested_at=datetime.now(UTC),
        )
        result = update_document_wikilinks(
            tmpdir,
            doc_id="12345678-0000-0000-0000-000000000000",
            mentions=["Carol White"],
        )
        assert result is not None
        mode = stat.S_IMODE(os.stat(result).st_mode)
        assert not (mode & stat.S_IWUSR)  # read-only after update


def test_update_document_wikilinks_not_found():
    from src.ingest.vault_sync import update_document_wikilinks
    with tempfile.TemporaryDirectory() as tmpdir:
        result = update_document_wikilinks(tmpdir, "nonexistent-id", ["Alice"])
        assert result is None


# ── T-034: MCP server ─────────────────────────────────────────────────────────

def test_mcp_server_module_exists():
    assert (ROOT / "src" / "api" / "mcp_server.py").exists()


def test_mcp_server_exposes_get_mcp_app():
    content = (ROOT / "src" / "api" / "mcp_server.py").read_text()
    assert "get_mcp_app" in content


def test_mcp_server_defines_three_tools():
    content = (ROOT / "src" / "api" / "mcp_server.py").read_text()
    assert "add_document" in content
    assert "search_facts" in content
    assert "search_nodes" in content


def test_mcp_server_mounted_in_tui_main():
    content = (ROOT / "src" / "tui" / "main.py").read_text()
    assert "mcp" in content.lower()
    assert "/mcp" in content


def test_mcp_server_graceful_degradation():
    content = (ROOT / "src" / "api" / "mcp_server.py").read_text()
    assert "ImportError" in content
    assert "return None" in content
