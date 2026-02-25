"""Tests for T-017 (retry), T-018 (vault sync), T-019 (TUI screens)."""
import os
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from src.ingest.retry import MAX_RETRIES, RETRY_DELAYS
from src.ingest.vault_sync import write_document_note, write_person_note

ROOT = Path(__file__).parent.parent


# ── T-017: Dead-letter retry ───────────────────────────────────────────────

def test_retry_delays_are_2_8_32():
    assert RETRY_DELAYS == [2, 8, 32]


def test_max_retries_matches_delays():
    assert len(RETRY_DELAYS) == MAX_RETRIES
    assert MAX_RETRIES == 3


# ── T-018: Vault sync ──────────────────────────────────────────────────────

def test_write_person_note_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = write_person_note(tmpdir, email="alice@example.com", display_name="Alice Smith")
        assert path.exists()
        content = path.read_text()
        assert "alice_example.com" in content or "alice@example.com" in content
        assert "Alice Smith" in content


def test_write_person_note_has_yaml_frontmatter():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = write_person_note(tmpdir, email="bob@example.com", display_name="Bob")
        content = path.read_text()
        assert content.startswith("---")
        assert "email:" in content


def test_write_person_note_chmod_444():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = write_person_note(tmpdir, email="alice@example.com", display_name="Alice")
        file_stat = os.stat(path)
        mode = stat.S_IMODE(file_stat.st_mode)
        # Should be readable but not writable
        assert mode & stat.S_IRUSR   # owner read
        assert not (mode & stat.S_IWUSR)  # owner NOT writable


def test_write_document_note_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = write_document_note(
            tmpdir,
            doc_id="abc-123",
            source_path="/drop-zone/inbox.mbox",
            source_type="mbox",
            sender_email="alice@example.com",
            subject="Q3 Budget Review",
            ingested_at=datetime(2024, 9, 12, tzinfo=UTC),
        )
        assert path.exists()
        content = path.read_text()
        assert "Q3 Budget Review" in content
        assert "alice_example.com" in content or "alice@example.com" in content


def test_write_document_note_chmod_444():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = write_document_note(
            tmpdir,
            doc_id="xyz-999",
            source_path="/drop-zone/test.pdf",
            source_type="pdf",
            sender_email="test@example.com",
            subject="Test",
            ingested_at=datetime.now(UTC),
        )
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert not (mode & stat.S_IWUSR)  # read-only


def test_vault_sync_persons_subdirectory():
    with tempfile.TemporaryDirectory() as tmpdir:
        write_person_note(tmpdir, email="test@example.com", display_name="Test")
        assert (Path(tmpdir) / "persons").is_dir()


def test_vault_sync_documents_subdirectory():
    with tempfile.TemporaryDirectory() as tmpdir:
        write_document_note(
            tmpdir, doc_id="d1", source_path="/x", source_type="pdf",
            sender_email="a@b.com", subject="S", ingested_at=datetime.now(UTC)
        )
        assert (Path(tmpdir) / "documents").is_dir()


# ── T-019: TUI screens structural checks ──────────────────────────────────

def test_intake_screen_exists():
    assert (ROOT / "src" / "tui" / "screens" / "intake.py").exists()


def test_search_screen_exists():
    assert (ROOT / "src" / "tui" / "screens" / "search.py").exists()


def test_intake_screen_has_required_bindings():
    content = (ROOT / "src" / "tui" / "screens" / "intake.py").read_text()
    for key in ['"d"', '"p"', '"r"', '"s"']:
        assert key in content, f"Missing binding {key} in intake.py"


def test_search_screen_has_editor_binding():
    content = (ROOT / "src" / "tui" / "screens" / "search.py").read_text()
    assert '"e"' in content
    assert "obsidian" in content.lower()
    assert "EDITOR" in content


def test_search_screen_calls_post_search():
    content = (ROOT / "src" / "tui" / "screens" / "search.py").read_text()
    assert "/search" in content
    assert "bm25" in content.lower() or "BM25" in content


def test_search_screen_handles_degraded():
    content = (ROOT / "src" / "tui" / "screens" / "search.py").read_text()
    assert "degraded" in content.lower()
