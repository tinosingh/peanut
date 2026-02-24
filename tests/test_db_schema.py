"""Tests for T-001: init.sql schema integrity (no live DB needed)."""
from pathlib import Path

ROOT = Path(__file__).parent.parent
INIT_SQL = (ROOT / "db" / "init.sql").read_text()
ALEMBIC_INI = (ROOT / "alembic.ini").read_text()
ENV_PY = (ROOT / "db" / "migrations" / "env.py").read_text()


def test_init_sql_creates_all_tables():
    for table in ["documents", "persons", "chunks", "outbox", "dead_letter", "config"]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in INIT_SQL, f"Missing table: {table}"


def test_init_sql_has_extensions():
    assert "CREATE EXTENSION IF NOT EXISTS vector" in INIT_SQL
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in INIT_SQL


def test_init_sql_embedding_status_enum():
    assert "embedding_status_enum" in INIT_SQL
    assert "'pending'" in INIT_SQL
    assert "'processing'" in INIT_SQL
    assert "'done'" in INIT_SQL
    assert "'failed'" in INIT_SQL


def test_init_sql_hnsw_partial_index():
    assert "HNSW" in INIT_SQL
    assert "embedding_status = 'done'" in INIT_SQL


def test_init_sql_config_defaults():
    for key in ["bm25_weight", "vector_weight", "chunk_size", "chunk_overlap",
                "embed_model", "rrf_k", "embed_retry_max", "search_cache_ttl"]:
        assert key in INIT_SQL, f"Missing config key: {key}"
    assert "nomic-embed-text" in INIT_SQL


def test_init_sql_soft_delete_columns():
    assert "deleted_at  TIMESTAMPTZ" in INIT_SQL


def test_init_sql_outbox_schema():
    assert "processed_at TIMESTAMPTZ" in INIT_SQL
    assert "failed       BOOLEAN" in INIT_SQL
    assert "attempts     INT" in INIT_SQL


def test_alembic_uses_migrations_dir():
    assert "script_location = db/migrations" in ALEMBIC_INI


def test_alembic_env_reads_postgres_url():
    assert "POSTGRES_URL" in ENV_PY
    assert "postgresql+psycopg" in ENV_PY


def test_migrations_versions_dir_exists():
    assert (ROOT / "db" / "migrations" / "versions").is_dir()
