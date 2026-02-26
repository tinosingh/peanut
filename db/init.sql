-- Personal Knowledge Graph System — Bootstrap Schema
-- Applied once on first container start via /docker-entrypoint-initdb.d/
-- All subsequent changes: Alembic migrations in db/migrations/
-- Run: make migrate-up

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── Documents ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_path TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('mbox', 'pdf', 'markdown')),
    sha256      CHAR(64) NOT NULL,
    message_id  TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ,
    metadata    JSONB
);
-- Unique constraint:
-- 1. For non-mbox (message_id is NULL), sha256 must be unique.
-- 2. For mbox (message_id is NOT NULL), message_id must be unique.
CREATE UNIQUE INDEX IF NOT EXISTS documents_sha256_uniq_idx ON documents (sha256) WHERE message_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS documents_message_id_uniq_idx ON documents (message_id) WHERE message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS documents_active_idx
    ON documents (id) WHERE deleted_at IS NULL;

-- ── Persons ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS persons (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email        TEXT UNIQUE NOT NULL,
    display_name TEXT,
    pii          BOOLEAN NOT NULL DEFAULT true,
    merged_into  UUID REFERENCES persons(id),
    deleted_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS persons_active_idx
    ON persons (id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS persons_email_trgm_idx
    ON persons USING GIN (email gin_trgm_ops);

-- ── Chunks ─────────────────────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE embedding_status_enum AS ENUM ('pending', 'processing', 'done', 'failed');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS chunks (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id           UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index      INT NOT NULL,
    text             TEXT NOT NULL,
    tsv              TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    embedding        VECTOR(768),
    embedding_status embedding_status_enum NOT NULL DEFAULT 'pending',
    embedded_at      TIMESTAMPTZ,
    retry_count      INT NOT NULL DEFAULT 0,
    pii_detected     BOOLEAN NOT NULL DEFAULT false,
    token_count      INT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx
    ON chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS chunks_ann_idx
    ON chunks USING HNSW (embedding vector_cosine_ops)
    WHERE embedding_status = 'done';
CREATE INDEX IF NOT EXISTS chunks_pending_idx
    ON chunks (embedding_status) WHERE embedding_status = 'pending';
CREATE UNIQUE INDEX IF NOT EXISTS chunks_doc_idx_uniq
    ON chunks (doc_id, chunk_index);
CREATE INDEX IF NOT EXISTS chunks_pii_idx
    ON chunks (pii_detected) WHERE pii_detected = true;

-- ── Outbox ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outbox (
    id           BIGSERIAL PRIMARY KEY,
    event_type   TEXT NOT NULL,
    payload      JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    failed       BOOLEAN NOT NULL DEFAULT false,
    error        TEXT,
    attempts     INT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS outbox_unprocessed_idx
    ON outbox (created_at)
    WHERE processed_at IS NULL AND NOT failed;
CREATE INDEX IF NOT EXISTS outbox_drain_idx
    ON outbox (processed_at, failed, created_at)
    WHERE processed_at IS NULL AND NOT failed;

-- ── Dead letter ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dead_letter (
    id           SERIAL PRIMARY KEY,
    file_path    TEXT NOT NULL,
    error        TEXT NOT NULL,
    attempts     INT NOT NULL DEFAULT 1,
    last_attempt TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Config ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS config (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    value_type TEXT NOT NULL CHECK (value_type IN ('int', 'float', 'string')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO config (key, value, value_type) VALUES
    ('bm25_weight',       '0.5',               'float'),
    ('vector_weight',     '0.5',               'float'),
    ('chunk_size',        '512',               'int'),
    ('chunk_overlap',     '50',                'int'),
    ('embed_model',       'nomic-embed-text',  'string'),
    ('rrf_k',             '60',                'int'),
    ('embed_retry_max',   '5',                 'int'),
    ('search_cache_ttl',  '60',                'int')
ON CONFLICT (key) DO NOTHING;
