"""Tests for T-015 (embedding worker) + T-016 (outbox worker) — unit tests."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingest.embedding_worker import call_ollama_embed
from src.ingest.outbox_worker import OUTBOX_MAX_ATTEMPTS, _apply_outbox_event
from src.ingest.retry import MAX_RETRIES, retry_dead_letters
from src.shared.config import _DEFAULTS, get_config

# ── T-015: Embedding worker ────────────────────────────────────────────────

def test_embed_circuit_breaker_constants():
    """Embedding worker must have circuit breaker constants defined."""
    from src.ingest.embedding_worker import _CIRCUIT_BREAKER_BACKOFF, _CONSECUTIVE_ERROR_THRESHOLD
    assert _CONSECUTIVE_ERROR_THRESHOLD >= 5
    assert _CIRCUIT_BREAKER_BACKOFF >= 30


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
    # Batched into single Cypher query (sender + all recipients)
    assert mock_graph.query.call_count == 1
    cypher = mock_graph.query.call_args[0][0]
    assert "SENT" in cypher
    assert "RECEIVED" in cypher


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


# ── retry_dead_letters ─────────────────────────────────────────────────────

def _make_pool(fetchall_rows):
    """Build a mock AsyncConnectionPool whose execute().fetchall() returns rows."""
    mock_cursor = AsyncMock()
    mock_cursor.fetchall.return_value = fetchall_rows

    mock_conn = AsyncMock()
    mock_conn.execute.return_value = mock_cursor

    mock_conn_ctx = AsyncMock()
    mock_conn_ctx.__aenter__.return_value = mock_conn
    mock_conn_ctx.__aexit__.return_value = False

    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn_ctx
    return mock_pool, mock_conn


@pytest.mark.asyncio
async def test_retry_dead_letters_recovers(tmp_path):
    """Successful handle_file call increments recovered count and DELETEs row."""
    test_file = tmp_path / "test.mbox"
    test_file.write_bytes(b"hello world")

    mock_pool, mock_conn = _make_pool([(42, str(test_file), 1)])
    handle_file = AsyncMock()

    result = await retry_dead_letters(mock_pool, handle_file)

    assert result == 1
    handle_file.assert_called_once()
    # The sha passed should be a hex string
    sha_arg = handle_file.call_args[0][1]
    assert len(sha_arg) == 64  # SHA-256 hex
    # DELETE should have been executed
    calls_sql = [str(c) for c in mock_conn.execute.call_args_list]
    assert any("DELETE FROM dead_letter" in s for s in calls_sql)


@pytest.mark.asyncio
async def test_retry_dead_letters_skips_over_max(tmp_path):
    """Rows with attempts > MAX_RETRIES are skipped without calling handle_file."""
    test_file = tmp_path / "test.mbox"
    test_file.write_bytes(b"hello world")

    mock_pool, _ = _make_pool([(99, str(test_file), MAX_RETRIES + 1)])
    handle_file = AsyncMock()

    result = await retry_dead_letters(mock_pool, handle_file)

    assert result == 0
    handle_file.assert_not_called()


@pytest.mark.asyncio
async def test_retry_dead_letters_updates_on_failure(tmp_path):
    """When handle_file raises, attempts is incremented and recovered stays 0."""
    test_file = tmp_path / "test.mbox"
    test_file.write_bytes(b"hello world")

    mock_pool, mock_conn = _make_pool([(7, str(test_file), 1)])
    handle_file = AsyncMock(side_effect=RuntimeError("embed failed"))

    result = await retry_dead_letters(mock_pool, handle_file)

    assert result == 0
    calls_sql = [str(c) for c in mock_conn.execute.call_args_list]
    assert any("UPDATE dead_letter" in s for s in calls_sql)


# ── get_config ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_config_returns_db_values():
    """get_config coerces int/float values from DB rows correctly."""
    rows = [("rrf_k", "30", "int"), ("bm25_weight", "0.7", "float"), ("embed_model", "my-model", "str")]
    mock_pool, _ = _make_pool(rows)

    config = await get_config(mock_pool)

    assert config["rrf_k"] == 30
    assert config["bm25_weight"] == pytest.approx(0.7)
    assert config["embed_model"] == "my-model"


@pytest.mark.asyncio
async def test_get_config_falls_back_to_defaults():
    """get_config returns _DEFAULTS when DB raises."""
    mock_pool = MagicMock()
    mock_pool.connection.side_effect = RuntimeError("db down")

    config = await get_config(mock_pool)

    assert config == _DEFAULTS
