"""Tests for T-015 (embedding worker) + T-016 (outbox worker) — unit tests."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingest.embedding_worker import EMBED_QUEUE, call_ollama_embed
from src.ingest.outbox_worker import _apply_outbox_event, OUTBOX_MAX_ATTEMPTS


# ── T-015: Embedding worker ────────────────────────────────────────────────

def test_embed_queue_bounded():
    """EMBED_QUEUE maxsize must be 500 (backpressure guard)."""
    assert EMBED_QUEUE.maxsize == 500


@pytest.mark.asyncio
async def test_call_ollama_embed_parses_response():
    """call_ollama_embed should return a list of vectors from Ollama."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await call_ollama_embed("http://localhost:11434", "nomic-embed-text",
                                         ["text1", "text2"])

    assert len(result) == 2
    assert result[0] == [0.1, 0.2, 0.3]


def test_embedding_worker_uses_for_update_skip_locked():
    code = (Path(__file__).parent.parent / "src" / "ingest" / "embedding_worker.py").read_text()
    assert "FOR UPDATE SKIP LOCKED" in code


def test_embedding_worker_handles_retry_max():
    code = (Path(__file__).parent.parent / "src" / "ingest" / "embedding_worker.py").read_text()
    assert "'failed'" in code
    assert "retry_max" in code


def test_embedding_worker_uses_processing_status():
    code = (Path(__file__).parent.parent / "src" / "ingest" / "embedding_worker.py").read_text()
    assert "'processing'" in code


# ── T-016: Outbox worker ───────────────────────────────────────────────────

def test_outbox_max_attempts_is_10():
    assert OUTBOX_MAX_ATTEMPTS == 10


def test_apply_outbox_document_added():
    """_apply_outbox_event should call graph.query for document_added."""
    mock_graph = MagicMock()
    payload = {
        "doc_id": "doc-123",
        "source_path": "/drop-zone/test.mbox",
        "source_type": "mbox",
        "ingested_at": "2024-01-01T00:00:00Z",
        "sender": {"email": "alice@example.com", "name": "Alice", "id": "person-1"},
        "recipients": [{"email": "bob@example.com", "field": "to"}],
    }
    _apply_outbox_event(mock_graph, "document_added", payload)
    # Should be called twice: once for SENT, once for RECEIVED
    assert mock_graph.query.call_count == 2


def test_apply_outbox_entity_deleted():
    mock_graph = MagicMock()
    _apply_outbox_event(mock_graph, "entity_deleted", {"id": "person-123"})
    mock_graph.query.assert_called_once()
    assert "DETACH DELETE" in mock_graph.query.call_args[0][0]


def test_apply_outbox_person_merged():
    mock_graph = MagicMock()
    _apply_outbox_event(mock_graph, "person_merged",
                        {"from_id": "old-id", "ts": "2024-01-01T00:00:00Z"})
    mock_graph.query.assert_called_once()
    assert "invalid_at" in mock_graph.query.call_args[0][0]


def test_outbox_worker_polls_unprocessed():
    code = (Path(__file__).parent.parent / "src" / "ingest" / "outbox_worker.py").read_text()
    assert "processed_at IS NULL" in code
    assert "NOT failed" in code


def test_outbox_worker_dead_letters_after_max_attempts():
    code = (Path(__file__).parent.parent / "src" / "ingest" / "outbox_worker.py").read_text()
    assert "failed = true" in code
    assert "max attempts exceeded" in code
