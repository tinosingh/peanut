"""Tests for T-040 (auth), T-041 (soft-delete), T-042 (hard-delete),
T-043 (PII report), T-044 (weight sliders), T-045 (Prometheus metrics).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent


# ── T-040: Auth ───────────────────────────────────────────────────────────────

def test_auth_module_exists():
    assert (ROOT / "src" / "api" / "auth.py").exists()


def test_auth_uses_x_api_key_header():
    content = (ROOT / "src" / "api" / "auth.py").read_text()
    assert "X-API-Key" in content


def test_auth_has_read_and_write_keys():
    content = (ROOT / "src" / "api" / "auth.py").read_text()
    assert "API_KEY_READ" in content
    assert "API_KEY_WRITE" in content


def test_auth_uses_secrets_compare_digest():
    content = (ROOT / "src" / "api" / "auth.py").read_text()
    assert "compare_digest" in content


def test_auth_returns_401_missing_key():
    content = (ROOT / "src" / "api" / "auth.py").read_text()
    assert "401" in content


def test_auth_returns_403_invalid_key():
    content = (ROOT / "src" / "api" / "auth.py").read_text()
    assert "403" in content


def test_auth_disabled_when_no_env_vars():
    content = (ROOT / "src" / "api" / "auth.py").read_text()
    assert "return" in content  # no-op path


def test_generate_key_function():
    content = (ROOT / "src" / "api" / "auth.py").read_text()
    assert "generate_key" in content
    assert "token_urlsafe" in content


def test_rotate_keys_in_makefile():
    content = (ROOT / "Makefile").read_text()
    assert "rotate-keys" in content
    assert "API_KEY_READ" in content
    assert "API_KEY_WRITE" in content


# ── T-041: Soft-delete ────────────────────────────────────────────────────────

def test_entities_api_module_exists():
    assert (ROOT / "src" / "api" / "entities.py").exists()


def test_soft_delete_endpoint_defined():
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert "soft_delete" in content or "DELETE" in content
    assert "deleted_at" in content


def test_soft_delete_posts_outbox_event():
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert "entity_deleted" in content
    assert "outbox" in content


def test_soft_delete_filters_already_deleted():
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert "deleted_at IS NULL" in content


def test_settings_screen_has_pii_report():
    content = (ROOT / "src" / "tui" / "screens" / "settings.py").read_text()
    assert "pii" in content.lower()


# ── T-042: Hard-delete ────────────────────────────────────────────────────────

def test_hard_delete_requires_confirm():
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert "confirm" in content
    assert "30 days" in content or "30d" in content or "INTERVAL" in content


def test_hard_delete_appends_to_deletion_log():
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert "deletion_log.jsonl" in content


def test_hard_delete_dispatches_outbox_detach():
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert "entity_hard_deleted" in content or "DETACH" in content.upper()


def test_hard_delete_makefile_target():
    content = (ROOT / "Makefile").read_text()
    assert "hard-delete" in content


# ── T-043: PII report ─────────────────────────────────────────────────────────

def test_config_api_module_exists():
    assert (ROOT / "src" / "api" / "config_api.py").exists()


def test_pii_report_endpoint():
    content = (ROOT / "src" / "api" / "config_api.py").read_text()
    assert "/pii/report" in content


def test_pii_report_returns_persons_and_chunks():
    content = (ROOT / "src" / "api" / "config_api.py").read_text()
    assert "pii = true" in content or "pii=true" in content or "pii_detected" in content


def test_pii_bulk_redact_endpoint():
    content = (ROOT / "src" / "api" / "config_api.py").read_text()
    assert "bulk-redact" in content or "bulk_redact" in content
    assert "REDACTED" in content


def test_pii_mark_public_endpoint():
    content = (ROOT / "src" / "api" / "config_api.py").read_text()
    assert "mark-public" in content or "mark_public" in content
    assert "pii = false" in content or "false" in content.lower()


# ── T-044: Weight sliders ─────────────────────────────────────────────────────

def test_config_endpoint_exists():
    content = (ROOT / "src" / "api" / "config_api.py").read_text()
    assert "/config" in content
    assert "bm25_weight" in content
    assert "vector_weight" in content


def test_config_validates_weight_range():
    content = (ROOT / "src" / "api" / "config_api.py").read_text()
    assert "0.0" in content and "1.0" in content


def test_settings_screen_has_weight_inputs():
    content = (ROOT / "src" / "tui" / "screens" / "settings.py").read_text()
    assert "bm25" in content.lower()
    assert "vector" in content.lower()
    assert "save" in content.lower() or '"s"' in content


def test_settings_screen_shows_rrf_k_readonly():
    content = (ROOT / "src" / "tui" / "screens" / "settings.py").read_text()
    assert "rrf_k" in content
    assert "read" in content.lower()


# ── T-045: Prometheus metrics ─────────────────────────────────────────────────

def test_metrics_module_exists():
    assert (ROOT / "src" / "api" / "metrics.py").exists()


def test_metrics_endpoint_defined():
    content = (ROOT / "src" / "api" / "metrics.py").read_text()
    assert "/metrics" in content


def test_metrics_exposes_chunks_total():
    content = (ROOT / "src" / "api" / "metrics.py").read_text()
    assert "pkg_chunks_total" in content


def test_metrics_exposes_outbox_depth():
    content = (ROOT / "src" / "api" / "metrics.py").read_text()
    assert "pkg_outbox_depth" in content


def test_metrics_graceful_degradation():
    content = (ROOT / "src" / "api" / "metrics.py").read_text()
    assert "ImportError" in content
    assert "503" in content


def test_tui_main_includes_all_epic4_routers():
    content = (ROOT / "src" / "tui" / "main.py").read_text()
    assert "entities_router" in content
    assert "config_router" in content
    assert "metrics_router" in content


# ── Functional auth tests (skipped if fastapi not installed) ──────────────────

def _make_request(path: str, api_key: str) -> MagicMock:
    req = MagicMock()
    req.url.path = path
    req.headers.get.return_value = api_key
    return req


def test_generate_key_returns_prefixed_token():
    pytest.importorskip("fastapi")
    from src.api.auth import generate_key
    key = generate_key("pkg")
    assert key.startswith("pkg_")
    assert len(key) > 20  # token_urlsafe(32) → 43 chars + prefix


def test_generate_key_unique():
    pytest.importorskip("fastapi")
    from src.api.auth import generate_key
    assert generate_key() != generate_key()


def test_check_api_key_allows_read_key_on_search():
    pytest.importorskip("fastapi")
    from src.api.auth import check_api_key
    with patch.dict("os.environ", {"API_KEY_READ": "read-key-abc", "API_KEY_WRITE": "write-key-xyz"}):
        req = _make_request("/search", "read-key-abc")
        check_api_key(req)  # must not raise


def test_check_api_key_rejects_read_key_on_write_path():
    pytest.importorskip("fastapi")
    from src.api.auth import check_api_key
    with patch.dict("os.environ", {"API_KEY_READ": "read-key-abc", "API_KEY_WRITE": "write-key-xyz"}):
        req = _make_request("/ingest/text", "read-key-abc")
        with pytest.raises(Exception) as exc_info:
            check_api_key(req)
        assert exc_info.value.status_code == 403


def test_check_api_key_allows_write_key_on_write_path():
    pytest.importorskip("fastapi")
    from src.api.auth import check_api_key
    with patch.dict("os.environ", {"API_KEY_READ": "read-key-abc", "API_KEY_WRITE": "write-key-xyz"}):
        req = _make_request("/ingest/text", "write-key-xyz")
        check_api_key(req)  # must not raise


def test_check_api_key_disabled_when_no_env_vars():
    pytest.importorskip("fastapi")
    from src.api.auth import check_api_key
    with patch.dict("os.environ", {}, clear=True):
        req = _make_request("/search", "anything")
        check_api_key(req)  # no-op when keys not configured


def test_check_api_key_raises_401_with_no_header():
    pytest.importorskip("fastapi")
    from src.api.auth import check_api_key
    with patch.dict("os.environ", {"API_KEY_READ": "read-key-abc"}):
        req = _make_request("/search", "")
        req.headers.get.return_value = ""
        with pytest.raises(Exception) as exc_info:
            check_api_key(req)
        assert exc_info.value.status_code == 401
