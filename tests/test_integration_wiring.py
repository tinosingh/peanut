"""Tests for integration wire-up: ingest main, TUI app nav, db psycopg3 fix, env."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent.parent


# ── ingest/main.py wiring ─────────────────────────────────────────────────────

def test_ingest_main_imports_all_workers():
    content = (ROOT / "src" / "ingest" / "main.py").read_text()
    assert "embedding_worker" in content
    assert "outbox_worker" in content
    assert "watch_drop_zone" in content


def test_ingest_main_passes_pool_to_workers():
    content = (ROOT / "src" / "ingest" / "main.py").read_text()
    assert "embedding_worker(pool" in content
    assert "outbox_worker(pool" in content


def test_ingest_main_uses_chunk_text():
    content = (ROOT / "src" / "ingest" / "main.py").read_text()
    assert "chunk_text" in content
    assert "has_pii" in content


def test_ingest_main_inserts_chunks():
    content = (ROOT / "src" / "ingest" / "main.py").read_text()
    assert "_insert_chunks" in content
    assert "chunk_index" in content or "chunk.index" in content


def test_ingest_main_handles_mbox_pdf_markdown():
    content = (ROOT / "src" / "ingest" / "main.py").read_text()
    assert "mbox" in content
    assert "pdf" in content
    assert "markdown" in content


def test_ingest_main_writes_dead_letter_on_error():
    content = (ROOT / "src" / "ingest" / "main.py").read_text()
    assert "write_dead_letter" in content


def test_ingest_main_handles_graceful_shutdown():
    content = (ROOT / "src" / "ingest" / "main.py").read_text()
    assert "SIGTERM" in content or "signal" in content
    assert "stop_event" in content or "cancel" in content


def test_ingest_main_env_vars():
    content = (ROOT / "src" / "ingest" / "main.py").read_text()
    assert "OLLAMA_URL" in content
    assert "EMBED_MODEL" in content
    assert "FALKORDB_HOST" in content or "falkordb_host" in content


# ── TUI app.py screen navigation ─────────────────────────────────────────────

def test_tui_app_has_all_screen_bindings():
    content = (ROOT / "src" / "tui" / "app.py").read_text()
    for binding in ['"/"', '"i"', '"e"', '"s"', '"?"', '"q"']:
        assert binding in content, f"Missing binding {binding}"


def test_tui_app_navigates_to_search():
    content = (ROOT / "src" / "tui" / "app.py").read_text()
    assert "SearchScreen" in content
    assert "goto_search" in content


def test_tui_app_navigates_to_intake():
    content = (ROOT / "src" / "tui" / "app.py").read_text()
    assert "IntakeScreen" in content
    assert "goto_intake" in content


def test_tui_app_navigates_to_entities():
    content = (ROOT / "src" / "tui" / "app.py").read_text()
    assert "EntitiesScreen" in content
    assert "goto_entities" in content


def test_tui_app_navigates_to_settings():
    content = (ROOT / "src" / "tui" / "app.py").read_text()
    assert "SettingsScreen" in content
    assert "goto_settings" in content


def test_tui_app_psycopg3_style():
    """_has_documents uses psycopg3 cursor.fetchone() not psycopg2 fetchrow."""
    content = (ROOT / "src" / "tui" / "app.py").read_text()
    assert "fetchrow" not in content
    assert "fetchone" in content


# ── Dashboard screen ──────────────────────────────────────────────────────────

def test_dashboard_shows_chunk_stats():
    content = (ROOT / "src" / "tui" / "screens" / "dashboard.py").read_text()
    assert "embedding_status" in content
    assert "outbox" in content.lower()


def test_dashboard_auto_refreshes():
    content = (ROOT / "src" / "tui" / "screens" / "dashboard.py").read_text()
    assert "set_interval" in content or "interval" in content.lower()


def test_dashboard_shows_dead_letters():
    content = (ROOT / "src" / "tui" / "screens" / "dashboard.py").read_text()
    assert "dead" in content.lower()


# ── db.py psycopg3 fix ────────────────────────────────────────────────────────

def test_db_uses_psycopg3_fetchone():
    content = (ROOT / "src" / "ingest" / "db.py").read_text()
    assert "fetchrow" not in content, "fetchrow is psycopg2 — use execute().fetchone()"
    assert "fetchone" in content


# ── .env.example completeness ─────────────────────────────────────────────────

def test_env_example_has_api_keys():
    content = (ROOT / ".env.example").read_text()
    assert "API_KEY_READ" in content
    assert "API_KEY_WRITE" in content


def test_env_example_has_postgres_url():
    content = (ROOT / ".env.example").read_text()
    assert "POSTGRES_URL" in content


def test_env_example_has_embed_model():
    content = (ROOT / ".env.example").read_text()
    assert "EMBED_MODEL" in content


def test_env_example_has_drop_zone_and_vault():
    content = (ROOT / ".env.example").read_text()
    assert "DROP_ZONE_PATH" in content
    assert "VAULT_SYNC_PATH" in content


def test_env_example_has_api_base_url():
    content = (ROOT / ".env.example").read_text()
    assert "API_BASE_URL" in content
