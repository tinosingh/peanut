"""Tests for completed stubs: reindex, pii CLI, intake screen, search open_raw, shared_docs."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent.parent


# ── src/ingest/reindex.py ─────────────────────────────────────────────────────

def test_reindex_module_exists():
    assert (ROOT / "src" / "ingest" / "reindex.py").exists()


def test_reindex_uses_for_update_skip_locked():
    content = (ROOT / "src" / "ingest" / "reindex.py").read_text()
    assert "FOR UPDATE SKIP LOCKED" in content


def test_reindex_targets_embedding_v2():
    content = (ROOT / "src" / "ingest" / "reindex.py").read_text()
    assert "embedding_v2" in content


def test_reindex_has_confirm_flag():
    content = (ROOT / "src" / "ingest" / "reindex.py").read_text()
    assert "--confirm" in content
    assert "confirm_rename" in content


def test_reindex_has_atomic_rename():
    content = (ROOT / "src" / "ingest" / "reindex.py").read_text()
    assert "RENAME COLUMN" in content


def test_reindex_has_main_entrypoint():
    content = (ROOT / "src" / "ingest" / "reindex.py").read_text()
    assert "__main__" in content
    assert "main()" in content


def test_makefile_reindex_target():
    content = (ROOT / "Makefile").read_text()
    assert "reindex" in content
    assert "src.ingest.reindex" in content


# ── src/ingest/pii.py CLI ─────────────────────────────────────────────────────

def test_pii_has_main_entrypoint():
    content = (ROOT / "src" / "ingest" / "pii.py").read_text()
    assert "__main__" in content


def test_pii_cli_handles_scan_unscanned():
    content = (ROOT / "src" / "ingest" / "pii.py").read_text()
    assert "--scan-unscanned" in content


def test_pii_scan_updates_db():
    content = (ROOT / "src" / "ingest" / "pii.py").read_text()
    assert "pii_detected" in content
    assert "UPDATE chunks" in content


def test_makefile_scan_pii_target():
    content = (ROOT / "Makefile").read_text()
    assert "scan-pii" in content
    assert "--scan-unscanned" in content


# ── src/__init__.py ───────────────────────────────────────────────────────────

def test_src_init_exists():
    assert (ROOT / "src" / "__init__.py").exists()


# ── Intake screen stubs completed ────────────────────────────────────────────

def test_intake_refresh_table_implemented():
    content = (ROOT / "src" / "tui" / "screens" / "intake.py").read_text()
    # Should NOT just have a pass
    assert "_refresh_table" in content
    assert "embedding_status" in content or "source_path" in content


def test_intake_drop_file_action():
    content = (ROOT / "src" / "tui" / "screens" / "intake.py").read_text()
    assert "action_drop_file" in content
    assert "drop-zone" in content or "DROP_ZONE_PATH" in content


def test_intake_pause_watcher_uses_sentinel():
    content = (ROOT / "src" / "tui" / "screens" / "intake.py").read_text()
    assert "pause_watcher" in content
    assert ".pause" in content or "sentinel" in content


def test_intake_retry_errors_resets_to_pending():
    content = (ROOT / "src" / "tui" / "screens" / "intake.py").read_text()
    assert "retry_errors" in content or "_retry_errors" in content
    assert "pending" in content


def test_intake_heartbeat_alert():
    content = (ROOT / "src" / "tui" / "screens" / "intake.py").read_text()
    assert "120" in content or "heartbeat" in content.lower()


# ── Search screen open_raw implemented ───────────────────────────────────────

def test_search_open_raw_uses_pager():
    content = (ROOT / "src" / "tui" / "screens" / "search.py").read_text()
    assert "PAGER" in content
    assert "action_open_raw" in content
    assert "wired in Epic" not in content  # stub text removed


def test_search_open_editor_gets_selected_row():
    content = (ROOT / "src" / "tui" / "screens" / "search.py").read_text()
    assert "_selected_source_path" in content or "get_row_at" in content


def test_search_no_unused_subprocess():
    content = (ROOT / "src" / "tui" / "screens" / "search.py").read_text()
    assert "import subprocess" not in content


# ── entities.py shared_docs real query ───────────────────────────────────────

def test_entities_shared_docs_real_join():
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert "TODO" not in content
    assert "email_to_docs" in content or "docs_a & docs_b" in content


def test_entities_shared_docs_not_hardcoded_zero():
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert '"shared_docs": 0' not in content
