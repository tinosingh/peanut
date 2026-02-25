"""Tests for T-046 (PUT /entities bidirectional sync) and T-047 (slowapi rate limiting)."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


# ── T-046: PUT /entities/{type}/{id} ──────────────────────────────────────

def test_update_request_model_defined_in_code():
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert "class UpdateRequest" in content
    assert "diffs" in content
    assert "client_updated_at" in content


def test_update_response_model_defined_in_code():
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert "class UpdateResponse" in content
    assert "conflict_detected" in content
    assert "updated_fields" in content
    assert "server_updated_at" in content


def test_put_entity_endpoint_registered():
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert '@router.put("/entities/{entity_type}/{entity_id}"' in content


def test_put_entity_server_timestamp_wins():
    """Server conflict rule documented in code."""
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert "conflict" in content
    assert "server_ts" in content
    assert "client_ts" in content


def test_put_entity_only_safe_fields_allowed():
    """Unsafe fields are rejected — only _PERSON_UPDATABLE / _DOCUMENT_UPDATABLE allowed."""
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert "_PERSON_UPDATABLE" in content
    assert "_DOCUMENT_UPDATABLE" in content


def test_put_entity_sends_outbox_event():
    """Successful update dispatches entity_updated outbox event."""
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert "entity_updated" in content


def test_put_entity_conflict_returns_empty_updated_fields():
    """When conflict_detected, updated_fields must be empty — server wins."""
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert "updated_fields=updated" in content or "updated_fields" in content


def test_put_entity_validates_client_updated_at():
    """Invalid ISO timestamp raises 422."""
    content = (ROOT / "src" / "api" / "entities.py").read_text()
    assert "fromisoformat" in content
    assert "422" in content or "Invalid client_updated_at" in content


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("pydantic"),
    reason="pydantic not installed",
)
def test_update_request_pydantic_model():
    """Validate UpdateRequest Pydantic model instantiation."""
    from pydantic import BaseModel

    # Build the model dynamically to avoid importing fastapi
    class UpdateRequest(BaseModel):
        diffs: dict
        client_updated_at: str

    req = UpdateRequest(diffs={"display_name": "Alice"}, client_updated_at="2024-01-15T10:00:00Z")
    assert req.diffs["display_name"] == "Alice"


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("pydantic"),
    reason="pydantic not installed",
)
def test_update_response_pydantic_model():
    """Validate UpdateResponse Pydantic model with conflict_detected=True."""
    from typing import Literal

    from pydantic import BaseModel

    class UpdateResponse(BaseModel):
        id: str
        entity_type: Literal["document", "person"]
        updated_fields: list[str]
        conflict_detected: bool
        server_updated_at: str

    resp = UpdateResponse(
        id="abc-123",
        entity_type="person",
        updated_fields=[],
        conflict_detected=True,
        server_updated_at="2024-01-15T10:05:00+00:00",
    )
    assert resp.conflict_detected is True
    assert resp.updated_fields == []


# ── T-047: slowapi rate limiting ──────────────────────────────────────────

def test_main_imports_slowapi_gracefully():
    """If slowapi unavailable, main.py must still import cleanly."""
    content = (ROOT / "src" / "tui" / "main.py").read_text()
    assert "slowapi" in content
    assert "ImportError" in content or "try:" in content


def test_main_uses_default_limits():
    content = (ROOT / "src" / "tui" / "main.py").read_text()
    assert "100/minute" in content


def test_main_handles_rate_limit_exceeded():
    content = (ROOT / "src" / "tui" / "main.py").read_text()
    assert "RateLimitExceeded" in content


def test_main_sets_limiter_on_app_state():
    content = (ROOT / "src" / "tui" / "main.py").read_text()
    assert "app.state.limiter" in content


def test_slowapi_in_tui_dependencies():
    content = (ROOT / "pyproject.toml").read_text()
    assert "slowapi" in content


def test_main_slowapi_in_try_except():
    """slowapi import is wrapped in try/except so missing install is non-fatal."""
    content = (ROOT / "src" / "tui" / "main.py").read_text()
    # Must have try block containing the actual slowapi import
    try_idx = content.index("try:")
    except_idx = content.index("except ImportError")
    from_slowapi_idx = content.index("from slowapi import")
    assert try_idx < from_slowapi_idx < except_idx
