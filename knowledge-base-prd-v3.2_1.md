# Agile PRD: Personal Knowledge Graph System
### Postgres · FalkorDB · Ollama · Textual TUI · Docker

**Version:** 3.2 (Engineering + UX audit pass #2)
**Status:** Living Document
**Replaces:** v3.1
**Target Persona:** Technical solo operator, privacy-first, local inference preferred

---

## Changelog: v3.1 → v3.2

| # | Category | Change | Source |
|---|----------|--------|--------|
| 1 | Schema | Add Alembic migration framework in Epic 0; all schema changes via `make migrate-up` | Audit |
| 2 | Ops | Add `make restore-from-backup` + `make test-backup-restore` CI check | Audit |
| 3 | Graph | Clarify `:SENT` vs `:RECEIVED` edges; outbox payload carries `sender` + `recipients[]` | Audit |
| 4 | Config | Move `EMBED_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP` from `.env` into `config` table at init | Audit |
| 5 | TUI | First-run welcome screen when `documents` table is empty | Audit UX |
| 6 | TUI | Improve action microcopy; Textual footer bar describes focused action | Audit UX |
| 7 | TUI | `[X]` Export & Open Graph — generates `graph.html` (Vis.js) + `webbrowser.open()` | Audit UX |
| 8 | TUI | `E` key on vault files opens `obsidian://` URI; falls back to `$EDITOR` for non-vault files | Audit UX |

---

## Changelog: v3.0 → v3.1

| # | Category | Change | Source |
|---|----------|--------|--------|
| 1 | Schema | Add `outbox` table to Postgres for cross-service consistency (Postgres↔FalkorDB) | Audit: Critical |
| 2 | Schema | Add `embedding_status ENUM('pending','processing','done')` column to `chunks` | Audit: Critical |
| 3 | Schema | Add `deleted_at TIMESTAMPTZ` (soft-delete) to `documents` and `persons` | Audit: Critical |
| 4 | Schema | Add `pii_detected BOOLEAN` flag to `chunks` (PII in content, not just persons) | Audit: UX |
| 5 | Schema | Add `config` table to Postgres for runtime-tunable search weights (Epic 4) | Audit: Design |
| 6 | Logic | Outbox worker drains graph events atomically; FalkorDB failures stay in outbox | Audit: Critical |
| 7 | Logic | Embedding loop checks `embedding_status` to eliminate search-on-NULL race condition | Audit: Critical |
| 8 | Logic | Soft-delete → 30-day quarantine → hard delete with confirmation modal | Audit: Critical |
| 9 | Logic | PII scanner (spaCy + regex) during ingest flags chunks with `pii_detected=true` | Audit: UX |
| 10 | Logic | RRF clarified: pure rank fusion, no score weights; weighted fusion deferred to Epic 4 | Audit: Design |
| 11 | Logic | Jaro-Winkler threshold 0.90 now explicitly validated in Story 3.2 spike | Audit: Design |
| 12 | Logic | Chunk overlap 25/50/100-token A/B test added to Sprint 1 spike (Story 1.0) | Audit: Design |
| 13 | Logic | `make sanity` Makefile target — detects orphaned chunks on demand | Audit: Design |
| 14 | TUI | Search: `E` opens file in `$EDITOR`, `O` opens raw path, `Enter` expands inline | Audit: UX |
| 15 | TUI | Intake: "Last heartbeat Xs ago" per active file; alert if > 120 s stall | Audit: UX |
| 16 | TUI | Entities: merge queue row expands to show Jaro-Winkler score + matched fields | Audit: UX |
| 17 | TUI | Hard-delete: confirmation modal + two-keystroke confirmation required | Audit: UX |
| 18 | TUI | Settings screen: shows `EMBED_MODEL`, `CHUNK_OVERLAP`, `CHUNK_SIZE` as read-display from Sprint 2 | Audit: UX |
| 19 | TUI | Graph: Textual `Tree` widget replaces plain adjacency list | Audit: UX |
| 20 | TUI | `?` key toggles full key-binding help overlay on any screen | Audit: UX |
| 21 | TUI | Vault-sync files marked `chmod 444` (read-only) until Epic 4 write-back lands | Audit: Design |
| 22 | Backlog | `asyncio.Queue(maxsize=500)` bounded in-process queue for embedding backpressure | Audit: Architecture |
| 23 | Backlog | Story 4.3 split: 4.3a soft-delete, 4.3b hard-delete (30-day quarantine gate) | Audit: Critical |
| 24 | Backlog | Story 2.1 adds Pydantic `SearchRequest` with `q: str = Field(max_length=2000)` | Audit: Critical |

---

## 1. Product Vision & Core Philosophy

A self-hosted, containerised personal knowledge system that transforms raw personal data (emails, documents, PDFs, notes) into a queryable semantic knowledge graph — surfaced through Obsidian as the primary reading interface and a Textual TUI as the operational control plane.

**Why TUI over GUI?** A TUI (Textual 8.x) ships inside a container without a display server, works over SSH, and avoids a full web frontend. A web UI is out of scope until the TUI proves insufficient.

**Why Docker-first?** Dependency isolation. A compose stack eliminates "works on my machine" failures and makes the system portable across workstations.

**Stack philosophy (KISS + LEAN):** One Postgres instance with `pgvector` replaces three separate services (MySQL + Elasticsearch + Milvus). FalkorDB is a single container running on Redis that replaces OpenMetadata's lineage graph. The result is 4 services instead of 7.

---

## 2. Riskiest Assumptions (Ordered by Lethality)

| # | Assumption | Validation Method | Kill Criteria |
|---|-----------|------------------|---------------|
| 1 | Raw MBOX/PDF extracts yield useful searchable text | Sprint 1 spike: operator manually finds 5 known emails by keyword. Pass = all 5 found in < 5 s | Any email not findable |
| 2 | Ollama `nomic-embed-text` is fast enough for interactive use | Sprint 1 spike: embed 1 000 chunks, measure p95 latency on target hardware | p95 > 3 s per query |
| 3 | Obsidian file-based vault sync won't corrupt the vault | Manual destructive-write test at end of Epic 2 | Any silent data loss |
| 4 | TUI intake reduces friction enough for consistent daily use | Weekly self-usage review for 30 days post-Epic 1 | Operator skips ingest 3 weeks in a row |

---

## 3. System Architecture

### 3.1 Docker Compose Service Map

```
┌──────────────────────────────────────────────────────────────────┐
│                        docker-compose.yml                        │
│                                                                  │
│  ┌───────────────┐   ┌──────────────────┐   ┌────────────────┐  │
│  │ ingest-worker │   │   pkg-db         │   │   pkg-graph    │  │
│  │ (python:3.12) │──►│ pgvector 0.8.1   │   │ falkordb v4.14 │  │
│  │               │   │ pg17             │   │ (port 6379)    │  │
│  │ watchfiles    │   │ vectors+BM25     │◄──│                │  │
│  │ parsers       │   │ +metadata        │   └────────────────┘  │
│  │ chunker       │   │ +outbox          │          ▲            │
│  │ embedder      │   │ (port 5432)      │          │            │
│  └───────┬───────┘   └──────────────────┘          │            │
│          │                    ▲                     │            │
│          │                    │                     │            │
│          ▼                    │           ┌─────────┴──────────┐ │
│  ┌───────────────┐            │           │   tui-controller   │ │
│  │    ollama     │────────────┘           │ (python:3.12-slim) │ │
│  │  (port 11434) │  nomic-embed-text      │ Textual 8.x TUI    │ │
│  │  ollama:0.9.0 │  + reranker            │ FastAPI REST API   │ │
│  └───────────────┘                        │ (port 8000)        │ │
│                                           └────────────────────┘ │
│  Volumes: pkg_postgres  pkg_falkordb  pkg_ollama  pkg_ingest     │
└──────────────────────────────────────────────────────────────────┘
                               │
                 Host: ./drop-zone/  ./vault-sync/ (chmod 444 until Epic 4)
                 Obsidian reads ./vault-sync/ directly (no plugin, Epics 1–2)
```

### 3.2 Service Responsibilities

| Service | Image | Role |
|---------|-------|------|
| `ingest-worker` | `python:3.12-slim` | watchfiles loop; MBOX, PDF, Markdown parsers; chunker; PII scanner; embedding client; outbox drainer; graph writer |
| `pkg-db` | `pgvector/pgvector:0.8.1-pg17` | All relational data + BM25 (`tsvector`) + vector ANN (HNSW index) + outbox + config |
| `pkg-graph` | `falkordb/falkordb:v4.14.9` | Knowledge graph — Person, Document, Concept nodes; typed edges with `valid_at`/`invalid_at` |
| `ollama` | `ollama/ollama:0.9.0` | Local embeddings only (`nomic-embed-text`). **Not used for reranking.** |
| `tui-controller` | `python:3.12-slim` | Textual 8.x TUI + FastAPI REST (port 8000). Runs CrossEncoder reranker **in-process** via `sentence-transformers`. |

> **Reranker execution model:** CrossEncoder (`cross-encoder/ms-marco-MiniLM-L6-v2`) loads inside the `tui-controller` Python process via `sentence-transformers`. It does **not** run via Ollama. Memory budget for `tui-controller`: ~500 MB baseline + ~350 MB CrossEncoder model = ~850 MB peak. Size your container accordingly.

> **ARM / Apple Silicon:** All four images publish `linux/arm64` manifests. No Rosetta emulation needed.

> **Embedding alternative:** `all-minilm` (Ollama) is a lighter fallback if `nomic-embed-text` is too slow. Swap via `EMBED_MODEL=all-minilm` env var — no code change.

### 3.3 Data Flow

```
./drop-zone/  (host bind mount)
      │
      ▼
ingest-worker
      │ 1. watchfiles.awatch() detects new file
      │ 2. magika fallback for ambiguous extensions → choose parser
      │ 3. parse: mailbox (MBOX) | pdfminer.six (PDF) | markdown (MD)
      │ 4. chunk: 512 tokens / 50-token overlap (validated in Sprint 1 spike)
      │ 5. hash (SHA-256) → skip if already in pkg-db (dedup)
      │ 6. PII scan: spaCy + regex → set chunk.pii_detected
      │
      ├──► pkg-db (Postgres/pgvector) — single transaction:
      │      INSERT INTO documents / persons (UPSERT)
      │      INSERT INTO chunks (embedding_status='pending')
      │      INSERT INTO outbox (event_type='document_added', payload)
      │      ← graph write deferred to outbox worker (see §4.9)
      │
      └──► ./vault-sync/ chmod 444  (Markdown files for Obsidian, Epics 1–2)

Outbox worker (asyncio.Task inside ingest-worker):
      polls outbox WHERE processed_at IS NULL
      → writes to FalkorDB (Cypher MERGE/CREATE)
      → marks outbox row processed_at = now()
      → on FalkorDB failure: leaves row, retries with backoff

Embedding worker (asyncio.Task inside ingest-worker):
      polls chunks WHERE embedding_status='pending' LIMIT 200
      → sets embedding_status='processing' (prevents double-pick)
      → calls Ollama /api/embed
      → sets embedding, embedded_at, embedding_status='done'
      → on failure: sets embedding_status='pending', increments retry_count

Query path:
  TUI / Obsidian plugin (Epic 3+)
      │
      ▼
  tui-controller (FastAPI)
      │ POST /search  { "q": "...", "limit": 10 }  ← Pydantic validated, max_length=2000
      ├──► pkg-db: BM25 (tsvector @@ plainto_tsquery) → top 50
      ├──► pkg-db: ANN (embedding <=> $query_vec) WHERE embedding_status='done'
      │    RRF merge (k=60, pure rank fusion — no score weights) → top 20
      └──► Ollama CrossEncoder rerank → top 10 (graceful degradation if unavailable)
```

### 3.4 Schema: Postgres

> **Migration management:** `init.sql` bootstraps the schema on first container start. All subsequent schema changes (e.g., Story 2.3's `embedding_v2` column) are managed via **Alembic** migrations, introduced in Epic 0. `make migrate-up` applies pending migrations. Never hand-edit a running schema — always add a migration file.

```sql
-- Run once at startup via init.sql mounted to /docker-entrypoint-initdb.d/

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- fuzzy name matching in entity resolution

-- ── Documents ──────────────────────────────────────────────────────────────
CREATE TABLE documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_path TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('mbox','pdf','markdown')),
    sha256      CHAR(64) UNIQUE NOT NULL,          -- dedup key
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ,                       -- soft-delete: non-NULL = quarantined
    metadata    JSONB
);
-- Partial index: all soft-delete-filtered queries use this; avoids full table scan
CREATE INDEX documents_active_idx ON documents (id) WHERE deleted_at IS NULL;

-- ── Persons ────────────────────────────────────────────────────────────────
CREATE TABLE persons (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email        TEXT UNIQUE NOT NULL,
    display_name TEXT,
    pii          BOOLEAN NOT NULL DEFAULT true,
    merged_into  UUID REFERENCES persons(id),     -- entity resolution audit trail
    deleted_at   TIMESTAMPTZ                       -- soft-delete
);
CREATE INDEX persons_active_idx ON persons (id) WHERE deleted_at IS NULL;

-- ── Chunks ─────────────────────────────────────────────────────────────────
CREATE TYPE embedding_status_enum AS ENUM ('pending', 'processing', 'done', 'failed');
-- 'failed': set after retry_count >= 5; chunk is excluded from embedding and surfaced in TUI error log

CREATE TABLE chunks (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id           UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index      INT NOT NULL,
    text             TEXT NOT NULL,
    tsv              TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    embedding        VECTOR(768),                  -- nomic-embed-text dimensions
    embedding_status embedding_status_enum NOT NULL DEFAULT 'pending',
    embedded_at      TIMESTAMPTZ,
    retry_count      INT NOT NULL DEFAULT 0,
    pii_detected     BOOLEAN NOT NULL DEFAULT false  -- spaCy/regex PII flag
);

CREATE INDEX chunks_tsv_idx  ON chunks USING GIN (tsv);
-- HNSW index only over completed embeddings
CREATE INDEX chunks_ann_idx  ON chunks USING HNSW (embedding vector_cosine_ops)
    WHERE embedding_status = 'done';
CREATE INDEX chunks_pending_idx ON chunks (embedding_status) WHERE embedding_status = 'pending';

-- ── Outbox (cross-service consistency) ─────────────────────────────────────
-- Written atomically in the same transaction as document/person inserts.
-- Outbox worker drains to FalkorDB; failure leaves row for retry.
CREATE TABLE outbox (
    id           BIGSERIAL PRIMARY KEY,
    event_type   TEXT NOT NULL,                   -- 'document_added', 'person_merged', 'entity_deleted'
    payload      JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,                     -- NULL = unprocessed; non-NULL = done
    failed       BOOLEAN NOT NULL DEFAULT false,  -- true = dead-lettered after OUTBOX_MAX_ATTEMPTS
    error        TEXT,                            -- last error message
    attempts     INT NOT NULL DEFAULT 0
);

-- Only poll rows that are unprocessed AND not dead-lettered
CREATE INDEX outbox_unprocessed_idx ON outbox (created_at) WHERE processed_at IS NULL AND NOT failed;

-- ── Dead letter ────────────────────────────────────────────────────────────
CREATE TABLE dead_letter (
    id           SERIAL PRIMARY KEY,
    file_path    TEXT NOT NULL,
    error        TEXT NOT NULL,
    attempts     INT NOT NULL DEFAULT 1,
    last_attempt TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Runtime config ────────────────────────────────────────────────────────────
-- Secrets (POSTGRES_PASSWORD, API keys) stay in .env.
-- Non-secret tuning params live here — readable/writable via TUI Settings screen.
-- Application reads embed_model, chunk_size, chunk_overlap from config at startup.
-- EMBED_MODEL env var is the bootstrap default only if the config row is absent.
CREATE TABLE config (
    key          TEXT PRIMARY KEY,
    value        TEXT NOT NULL,
    value_type   TEXT NOT NULL CHECK (value_type IN ('int', 'float', 'string')),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    -- Application validates: int/float keys must parse; string keys are used as-is.
    -- A bad value (e.g. chunk_size='abc') is caught at startup read, not silently at query time.
);

INSERT INTO config (key, value, value_type) VALUES
    ('bm25_weight',       '0.5',              'float'),
    ('vector_weight',     '0.5',              'float'),
    ('chunk_size',        '512',              'int'),
    ('chunk_overlap',     '50',               'int'),
    ('embed_model',       'nomic-embed-text', 'string'),
    ('rrf_k',             '60',               'int'),
    ('embed_retry_max',   '5',                'int'),
    ('search_cache_ttl',  '60',               'int');  -- seconds; 0 disables LRU cache
```

> **`GENERATED ALWAYS AS ... STORED`** requires Postgres 12+. pg17 supports it natively. The `tsv` column auto-updates on `text` change — no trigger needed (DRY).

> **HNSW partial index** (`WHERE embedding_status = 'done'`) prevents the ANN index from scanning NULL embeddings, eliminating the race condition between embedding worker and search queries.

### 3.5 Schema: FalkorDB (Cypher)

```cypher
// Node labels and required properties
// (:Person   {id, email, display_name, pii: true})
// (:Document {id, source_path, source_type, ingested_at})
// (:Concept  {id, label})              -- extracted via spaCy NER (Epic 3)

// Edge types with bi-temporal properties
// (:Person)-[:SENT        {valid_at, thread_id}]->(:Document)    -- sender only (1 per message)
// (:Person)-[:RECEIVED    {valid_at, thread_id, field}]->(:Document)  -- To/CC/BCC (N per message)
//   field = 'to' | 'cc' | 'bcc'
// (:Document)-[:REPLIES_TO {valid_at}]->(:Document)
// (:Person)-[:MENTIONS    {valid_at}]->(:Person)
// (:Document)-[:CONTAINS  {valid_at}]->(:Concept)

// invalid_at is SET on the edge when a fact becomes stale (Graphiti pattern)
// Omitted (NULL) means currently valid.
// Graph events arrive via the outbox worker — never written directly from ingest path.
```

> **Cardinality rule:** One `:SENT` edge from the sender. One `:RECEIVED` edge per recipient with `field` property (`to`/`cc`/`bcc`). The `document_added` outbox payload must carry `sender: str` and `recipients: list[{email, field}]`. `apply_outbox_event` loops through recipients to create all edges in a single transaction.

---

## 4. Key Library Usage (Correct API as of 2026)

### 4.1 watchfiles — file watcher

```python
# watchfiles 1.1.1
# Filter is a callable, not a set
import asyncio
from watchfiles import awatch, DefaultFilter

WATCHED_EXTENSIONS = {'.mbox', '.pdf', '.md', '.markdown', '.eml'}

class ExtFilter(DefaultFilter):
    def __call__(self, change, path: str) -> bool:
        return super().__call__(change, path) and \
               any(path.endswith(ext) for ext in WATCHED_EXTENSIONS)

async def watch_loop(drop_zone: str):
    async for changes in awatch(drop_zone, watch_filter=ExtFilter()):
        for change_type, path in changes:
            await handle_file(path)
```

### 4.2 magika — content-type detection (fallback only)

```python
# magika 1.0.1  — only called when file extension is absent or ambiguous
from magika import Magika

_magika = Magika()  # load once at startup

def detect_type(path: str) -> str:
    """Return 'mbox' | 'pdf' | 'markdown' | 'unknown'."""
    ext = path.rsplit('.', 1)[-1].lower() if '.' in path else ''
    if ext in ('mbox', 'mbx'):    return 'mbox'
    if ext == 'pdf':              return 'pdf'
    if ext in ('md', 'markdown'): return 'markdown'
    # Fallback: ask magika (1.0.1 API)
    result = _magika.identify_path(path)
    label = result.dl.ct_label           # ← 1.0.x accessor (was .output.ct_label in 0.x)
    if label == 'email':                 return 'mbox'
    if label == 'pdf':                   return 'pdf'
    if label in ('markdown', 'txt'):     return 'markdown'
    return 'unknown'
```

### 4.3 pgvector — vector operations

```python
# pgvector 0.4.2 with psycopg 3.x (NOT psycopg2)
# psycopg_pool.AsyncConnectionPool used in both services — prevents connection exhaustion
# if Ollama stalls and requests queue up. Pool size of 5 is sufficient for solo operator.
import psycopg
from psycopg_pool import AsyncConnectionPool
from pgvector.psycopg import register_vector  # ← psycopg3 path

async def create_pool(db_url: str) -> AsyncConnectionPool:
    pool = AsyncConnectionPool(db_url, min_size=2, max_size=5, open=False)
    await pool.open()
    async with pool.connection() as conn:
        await register_vector(conn)   # register once on pool creation
    return pool

async def upsert_chunk(pool, chunk_id, doc_id, chunk_index, text, pii_detected: bool):
    """Insert chunk with embedding_status='pending'. Embedding worker picks it up."""
    async with pool.connection() as conn:
        await conn.execute("""
            INSERT INTO chunks (id, doc_id, chunk_index, text, embedding_status, pii_detected)
            VALUES (%s, %s, %s, %s, 'pending', %s)
            ON CONFLICT (id) DO NOTHING
        """, (chunk_id, doc_id, chunk_index, text, pii_detected))

async def update_embedding(pool, chunk_id, embedding: list[float]):
    """Called by embedding worker after Ollama returns the vector."""
    async with pool.connection() as conn:
        await conn.execute("""
            UPDATE chunks
            SET embedding = %s, embedded_at = now(), embedding_status = 'done'
            WHERE id = %s
        """, (embedding, chunk_id))
```

### 4.4 sentence-transformers — CrossEncoder reranking

```python
# sentence-transformers 5.2.3
# CrossEncoder signature changed: use model_name kwarg
from sentence_transformers import CrossEncoder

_reranker: CrossEncoder | None = None

def get_reranker() -> CrossEncoder | None:
    global _reranker
    if _reranker is None:
        try:
            _reranker = CrossEncoder(model_name='cross-encoder/ms-marco-MiniLM-L6-v2')
        except Exception:
            return None   # graceful degradation — reranker is optional
    return _reranker

def rerank(query: str, candidates: list[str]) -> list[float] | None:
    reranker = get_reranker()
    if reranker is None or len(candidates) < 5:
        return None   # skip reranking on small result sets
    pairs = [(query, c) for c in candidates]
    return reranker.predict(pairs).tolist()
```

### 4.5 FalkorDB — graph writes (via outbox worker only)

```python
# falkordb 1.6.0
# Graph writes NEVER happen directly from ingest path.
# This function is called by the outbox worker after reading from the outbox table.
from falkordb import FalkorDB

db = FalkorDB(host='pkg-graph', port=6379)
g  = db.select_graph('pkg')

def apply_outbox_event(event_type: str, payload: dict) -> None:
    if event_type == 'document_added':
        g.query(
            "MERGE (p:Person {email: $email}) "
            "ON CREATE SET p.id = $pid, p.display_name = $name, p.pii = true "
            "MERGE (d:Document {id: $doc_id}) "
            "ON CREATE SET d.source_path = $path, d.source_type = $type, d.ingested_at = $ts "
            "MERGE (p)-[r:SENT {thread_id: $doc_id}]->(d) "
            "ON CREATE SET r.valid_at = $ts",
            payload
        )
    elif event_type == 'entity_deleted':
        g.query("MATCH (n {id: $id}) DETACH DELETE n", payload)
    elif event_type == 'person_merged':
        # Set invalid_at on all edges from the absorbed node
        g.query(
            "MATCH (a:Person {id: $from_id})-[r]->() SET r.invalid_at = $ts",
            payload
        )
```

### 4.6 Textual — TUI worker (Textual 8.x)

```python
# textual 8.0.0
# Sync functions: run_worker(thread=True)
# Async functions: run_worker() natively
from textual.app import App, ComposeResult
from textual.widgets import Tree
from textual.worker import Worker

class PKGApp(App):
    BINDINGS = [
        ("?", "toggle_help",    "Help"),
        ("e", "open_editor",    "Open in Obsidian or $EDITOR"),
        ("o", "open_raw",       "Open raw file in $PAGER"),
        ("x", "export_graph",   "Export graph as HTML"),
    ]

    def action_open_editor(self) -> None:
        """Open vault files in Obsidian via URI; others in $EDITOR."""
        path = self.get_focused_path()
        vault_sync = os.environ.get('VAULT_SYNC_PATH', './vault-sync')
        if path and path.startswith(os.path.abspath(vault_sync)):
            rel = os.path.relpath(path, vault_sync)
            vault_name = os.path.basename(vault_sync)
            uri = f"obsidian://open?vault={vault_name}&file={urllib.parse.quote(rel)}"
            webbrowser.open(uri)
        else:
            editor = os.environ.get('EDITOR', 'less')
            self.run_worker([editor, path], thread=True)

    def action_export_graph(self) -> None:
        """Generate graph.html (Vis.js) for current subgraph and open in browser."""
        self.run_worker(self._export_graph_html, thread=True)

    def _export_graph_html(self) -> None:
        nodes, edges = fetch_subgraph(self.current_root)
        html = render_visjs(nodes, edges)          # generates self-contained HTML
        out = Path('/tmp/pkg-graph.html')
        out.write_text(html)
        webbrowser.open(f'file://{out}')

```

### 4.7 Entity resolution — jellyfish

```python
# jellyfish 1.1.x
# Correct function name: jaro_winkler_similarity (not jaro_winkler_distance)
import jellyfish

def name_similarity(a: str, b: str) -> float:
    return jellyfish.jaro_winkler_similarity(a.lower(), b.lower())  # returns 0.0–1.0

# Threshold 0.90 is a starting point validated in Story 3.2 spike.
# Sprint 5 must run threshold sweep (0.80–0.99) against labeled pairs
# before hardcoding in production.
```

### 4.8 Hybrid search — Reciprocal Rank Fusion

```python
# RRF: pure rank-position fusion. No score weights applied here.
# Weighted fusion (BM25_score × w1 + ANN_score × w2) is a DIFFERENT algorithm
# deferred to Epic 4 Story 4.5 if empirical testing shows benefit.
# k is read from config table at query time (default 60); tunable via TUI Settings.

def rrf_merge(bm25_ids: list[str], ann_ids: list[str], k: int) -> list[str]:
    """Reciprocal Rank Fusion. k=60 is the literature default; read from config."""
    scores: dict[str, float] = {}
    for rank, id_ in enumerate(bm25_ids):
        scores[id_] = scores.get(id_, 0) + 1 / (k + rank + 1)
    for rank, id_ in enumerate(ann_ids):
        scores[id_] = scores.get(id_, 0) + 1 / (k + rank + 1)
    return sorted(scores, key=scores.__getitem__, reverse=True)
```

### 4.9 Outbox worker — cross-service consistency

```python
# Runs as a separate asyncio.Task inside ingest-worker.
# Guarantees: Postgres and FalkorDB converge even if FalkorDB was temporarily down.
# After OUTBOX_MAX_ATTEMPTS failures, row.failed is set to True — prevents infinite retry
# on permanent failures (e.g. FalkorDB schema change breaking event deserialization).

import asyncio, psycopg
from falkordb import FalkorDB

OUTBOX_POLL_INTERVAL = 2    # seconds
OUTBOX_BATCH_SIZE    = 50
OUTBOX_MAX_ATTEMPTS  = 10

async def outbox_worker(db_url: str, falkordb_host: str, falkordb_port: int):
    db = FalkorDB(host=falkordb_host, port=falkordb_port)
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        while True:
            rows = await conn.execute("""
                SELECT id, event_type, payload, attempts FROM outbox
                WHERE processed_at IS NULL AND NOT failed
                ORDER BY created_at
                LIMIT %s
            """, (OUTBOX_BATCH_SIZE,)).fetchall()

            for row_id, event_type, payload, attempts in rows:
                if attempts >= OUTBOX_MAX_ATTEMPTS:
                    # Dead-letter: set failed=true; excluded from future polls
                    await conn.execute("""
                        UPDATE outbox SET failed = true, error = 'max attempts exceeded'
                        WHERE id = %s
                    """, (row_id,))
                    await conn.commit()
                    continue
                try:
                    apply_outbox_event(event_type, payload)   # FalkorDB write
                    await conn.execute("""
                        UPDATE outbox SET processed_at = now(), attempts = attempts + 1
                        WHERE id = %s
                    """, (row_id,))
                except Exception as exc:
                    await conn.execute("""
                        UPDATE outbox SET error = %s, attempts = attempts + 1
                        WHERE id = %s
                    """, (str(exc), row_id))
                await conn.commit()

            await asyncio.sleep(OUTBOX_POLL_INTERVAL)
```

### 4.10 Embedding worker — bounded asyncio.Queue

```python
# Bounded queue provides backpressure: if Ollama is slow, ingest continues
# and chunks queue up to maxsize=500 before the watcher naturally slows.
# No external job queue service needed (KISS — this is all in-process).
# After embed_retry_max failures (config table, default 5), chunk status → 'failed'.
# This prevents infinite retry loops if Ollama returns systematic errors (OOM, model not loaded).
# Failed chunks are surfaced in TUI Dashboard error log.
#
# FOR UPDATE SKIP LOCKED ensures atomic claim even if the container is accidentally
# double-launched (e.g. restart overlap). Two workers will claim disjoint batches.

import asyncio

EMBED_QUEUE: asyncio.Queue = asyncio.Queue(maxsize=500)
INGEST_SEMAPHORE = asyncio.Semaphore(10)   # max 10 concurrent parse+insert tasks

async def embedding_worker(db_url: str, ollama_url: str, model: str, retry_max: int = 5):
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        while True:
            # Atomic claim: FOR UPDATE SKIP LOCKED prevents double-processing
            rows = await conn.execute("""
                UPDATE chunks SET embedding_status = 'processing'
                WHERE id IN (
                    SELECT id FROM chunks
                    WHERE embedding_status = 'pending'
                    ORDER BY id
                    LIMIT 200
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, text, retry_count
            """).fetchall()

            if not rows:
                await asyncio.sleep(1)
                continue

            ids          = [r[0] for r in rows]
            texts        = [r[1] for r in rows]
            retry_counts = {r[0]: r[2] for r in rows}

            try:
                embeddings = await call_ollama_embed(ollama_url, model, texts)
                for chunk_id, embedding in zip(ids, embeddings):
                    await update_embedding(conn, chunk_id, embedding)
            except Exception:
                # Increment retry_count; mark 'failed' if threshold exceeded
                for chunk_id in ids:
                    new_count  = retry_counts[chunk_id] + 1
                    new_status = 'failed' if new_count >= retry_max else 'pending'
                    await conn.execute("""
                        UPDATE chunks
                        SET embedding_status = %s, retry_count = %s
                        WHERE id = %s
                    """, (new_status, new_count, chunk_id))

            await conn.commit()
```

### 4.11 PII scanner — ingest-time chunk flagging

```python
# Runs during ingest, before chunks are inserted.
# Flags chunks that contain sensitive patterns (SSN, account numbers, health terms).
# Operator reviews flagged chunks in PII Report (Story 4.4, extended).

import re, spacy

_nlp = spacy.load('en_core_web_sm')   # loaded once at startup

_PII_PATTERNS = [
    re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),          # SSN
    re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b'),  # credit card
    re.compile(r'\b(diagnosis|prescription|medical record)\b', re.I),
]

def has_pii(text: str) -> bool:
    """Return True if text contains PII via spaCy PERSON entities or regex patterns."""
    doc = _nlp(text)
    if any(ent.label_ == 'PERSON' for ent in doc.ents):
        return True
    return any(p.search(text) for p in _PII_PATTERNS)
```

### 4.12 FastAPI input validation

```python
# tui-controller / api/search.py
from pydantic import BaseModel, Field
from fastapi import FastAPI

app = FastAPI()

class SearchRequest(BaseModel):
    q:     str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=100)

@app.post('/search')
async def search(req: SearchRequest):
    ...  # embedding + BM25 + RRF + rerank
```

---

## 5. TUI Design (Textual 8.x)

Accessed via:

```bash
docker exec -it pkg-tui python tui/app.py   # allocates fresh PTY
make tui                                     # Makefile shortcut
```

> **Do not use `docker attach`** — attaches to PID 1 without a PTY, garbles Textual rendering.

### 5.1 Screen Layout (120-column reference width; tested at 80 and 160)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  PKG  ·  v3.1  ·  [●] pg  [●] graph  [●] ollama  ·  ?=help  /=search  q=quit                                       │
├──────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────┤
│  NAVIGATION      │  MAIN PANEL                                                                                       │
│                  │                                                                                                   │
│  > Dashboard     │  📥 Drop Zone Monitor                                                                             │
│    Intake        │  Watching: /drop-zone/                                                                            │
│    Search        │                                                                                                   │
│    Entities      │  FILE                   STATUS        PROGRESS      HEARTBEAT    CHUNKS                           │
│    Graph         │  ────────────────────   ──────────    ──────────    ──────────   ──────                           │
│    Settings      │  export.mbox            Embedding     ████░░ 60%    2s ago       412                              │
│                  │  inbox.mbox             Parsing       ██░░░░ 30%    1s ago       —                                │
│  STATUS          │  notes.pdf              Done          ██████ 100%   —            847  ✓                           │
│  ─────────       │  ⚠ corrupt.mbox         Dead letter   —             3m ago ⚠     —                                │
│  Chunks:  18.2k  │                                                                                                   │
│  Pending:    41  │  [D Drop]  [P Pause]  [R Retry errors]  [S System / Full Reset]                                  │
│  Persons:  4821  │                                                                                                   │
│  Errors:      1  │                                                                                                   │
└──────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Heartbeat column:** Updates every second from the embedding worker's last progress write. If > 120 s with `embedding_status='processing'`, row turns amber and dashboard error count increments. Prevents silent stalls.

### 5.2 Screens

**Dashboard** — Service health (green/red per container via Docker SDK), chunk counts (total / pending / done), embedding queue depth (live `asyncio.Queue.qsize()` from ingest-worker), person count, last ingest timestamp, pipeline error log tail, outbox queue depth.

**Intake** — Drop Zone file queue. Per-file: `Pending → Parsing → Embedding → Indexed` with heartbeat timer. `[D]` drop file, `[P]` pause watcher, `[R]` retry dead letter, `[S]` system reset (calls `docker compose down -v && docker compose up` — avoids context switch to Makefile).

**Search** — Natural language query field. Results table:

```
 #  SOURCE FILE            SENDER              BM25   VEC   RERANK
 1  inbox.mbox (msg 412)   alice@example.com   0.87   0.91   0.94
 2  notes.pdf  (p.3)       —                   0.72   0.85   0.88
```

Key bindings: `E` opens file — if source is under `./vault-sync/`, constructs `obsidian://open?vault=vault-sync&file=<relative_path>` URI and opens in Obsidian; falls back to `$EDITOR` for non-vault files. `O` opens raw path in `$PAGER`. `Enter` expands chunk text inline. `↑↓` navigate. Footer bar describes the focused action in plain English.

**Entities** — Paginated list of `Person` nodes. Merge-candidate queue shows expanded evidence row on focus:

```
  ▶ CANDIDATE: alice@corp.com  ←→  alice.smith@personal.com
      Jaro-Winkler(display_name):  0.97  ✓
      Email domain match:          ✗
      Shared documents:            14
      [M Merge]  [X Dismiss]  [I Inspect documents]
```

No auto-merge. Operator must press `M` then confirm at a second prompt.

**Graph** — Cypher-driven subgraph rendered via Textual `Tree` widget:

```
  (:Person) alice@corp.com
  ├── [:SENT] → Document: "Q3 Budget Review" (2024-09-12)
  │   └── [:CONTAINS] → Concept: "quarterly review"
  ├── [:RECEIVED field=to] → Document: "Re: Q3 Budget Review"
  ├── [:MENTIONS] → Person: bob@corp.com
  └── [:SENT] → Document: "Budget Proposal" (2024-08-01)
```

`Enter` on a node sets it as the new root. `Backspace` returns to previous root. `X` exports the current subgraph as a self-contained `graph.html` (Vis.js, network layout) and opens it with `webbrowser.open()` — richer spatial visualisation without a web frontend.

**Settings** — Loaded from `config` Postgres table at screen mount. Read-display until Epic 4; writable in Story 4.5:

```
  EMBED_MODEL:     nomic-embed-text        [editable in Epic 4]
  CHUNK_SIZE:      512 tokens              [editable in Epic 4]
  CHUNK_OVERLAP:   50 tokens               [editable in Epic 4]
  BM25_WEIGHT:     0.5                     [editable in Story 4.5]
  VECTOR_WEIGHT:   0.5                     [editable in Story 4.5]
  VAULT_SYNC_PATH: ./vault-sync/
  PII REPORT:      [Open]
```

All values sourced from the `config` table — single source of truth. Even read-only, this screen is fully informative from Sprint 0.

**Help overlay** — Toggled by `?` on any screen. Lists all key bindings per screen. Implemented as a Textual `ModalScreen` overlay — one component, all screens share it.

**Soft-delete modal** — Any destructive action shows:

```
  ╔══════════════════════════════════════════════════╗
  ║  CONFIRM DELETE                                  ║
  ║                                                  ║
  ║  Entity:  alice@corp.com (Person)                ║
  ║  Chunks:  87 associated                          ║
  ║  Documents: 14 associated                        ║
  ║                                                  ║
  ║  This will move the entity to quarantine.        ║
  ║  Hard delete runs automatically after 30 days    ║
  ║  or via  make hard-delete --confirm              ║
  ║                                                  ║
  ║  [D Confirm soft-delete]          [Esc Cancel]   ║
  ╚══════════════════════════════════════════════════╝
```

---

## 6. Product Backlog

### Epic 0: Infrastructure Bootstrap *(Sprint 0 — 1 week)*

**Goal:** One command brings up the full stack. All services healthy. TUI shows green.

- **Story 0.1:** `docker compose up` starts all 4 services. Health checks pass.
  - *AC:* `docker compose ps` shows all 4 services `healthy` within 90 seconds on cold start.

- **Story 0.2:** `pkg-db` init: `init.sql` bootstraps all 6 tables with extensions and indexes. Alembic configured (`alembic.ini`, `env.py`) targeting `pkg-db`. `make migrate-up` applies pending migrations. All future schema changes (including Story 2.3's `embedding_v2`) are Alembic migration files — never hand-edited SQL on a running DB.
  - *AC:* `psql -c "\dt"` shows all 6 tables. `make migrate-up` exits 0 with "0 pending migrations" on a fresh init. A trivial test migration applies cleanly.

- **Story 0.3:** `pkg-graph` init: startup script creates the empty `pkg` graph.
  - *AC:* `redis-cli -p 6379 GRAPH.QUERY pkg "MATCH (n) RETURN count(n)"` returns 0.

- **Story 0.4:** Bind mounts: `./drop-zone/` (read-only in worker), `./vault-sync/` (write for worker, `chmod 444` on files written). Test file in `./drop-zone/` visible inside container.
  - *AC:* `docker exec ingest-worker ls /drop-zone/` shows test file. Files in `./vault-sync/` have mode `444`.

- **Story 0.5:** Makefile targets: `make up`, `make down`, `make reset`, `make logs`, `make tui`, `make backup`, `make restore-from-backup`, `make test-backup-restore`, `make migrate-up`, `make audit` (trivy), `make sanity` (orphaned-chunk check), `make hard-delete` (requires `--confirm`).
  - *AC:* Each target exits 0 on a fresh clone. `make sanity` returns "OK: 0 orphaned chunks". `make test-backup-restore` performs a full backup/restore cycle on a seeded test dataset and asserts row counts match before and after.

- **Story 0.6:** TUI `?` help overlay available from Sprint 0. Textual `BINDINGS` with descriptions auto-render a footer bar on every screen showing plain-English description of the focused action.
  - *AC:* Pressing `?` shows a modal listing all bindings. `Esc` closes it. Footer updates as focus moves between actions (e.g. focuses `[C]ancel Ingest` → footer reads "Cancel: Removes this file from the processing queue without deleting the source file").

- **Story 0.7:** First-run welcome screen: on launch, TUI checks `SELECT count(*) FROM documents`. If 0, shows a `WelcomeScreen` with: "Copy your files (PDF, MBOX, Markdown) into the `drop-zone/` folder to get started." Dismissed automatically after first successful ingest.
  - *AC:* Fresh install with empty DB shows welcome screen. After first file ingests successfully, subsequent launches show Dashboard.

**Definition of Done:** `make up && make tui` on a fresh clone → live dashboard with all services green within 3 minutes.

---

### Epic 1: Data Intake & Lexical Search *(Sprints 1–2)*

**Goal:** Drop a file → it becomes keyword-searchable. Vault sync writes Obsidian-ready Markdown.

- **Story 1.0 (Spike — Day 1 of Sprint 1):** Embed representative text chunks with `ollama nomic-embed-text` on target hardware at two scales: 1 000 chunks (warm path) and 10 000 chunks (scale path). Measure p95 latency per embedding call and per hybrid query at both scales. Test chunk overlap at 25, 50, and 100 tokens — plot Recall@5 for each. Compare `nomic-embed-text` vs `all-minilm` on the 10K batch for latency and Recall@5 delta.
  - *AC:* Results in `docs/perf-spike.md` covering both 1K and 10K scales. If p95 > 3 s at 1K, alternative model listed before Story 1.4 starts. If `nomic-embed-text` degrades significantly at 10K vs 1K, note the crossover point. Overlap recommendation documented with data.

- **Story 1.1:** `ingest-worker` uses `watchfiles 1.1.1` `awatch()` with `ExtFilter` for `.mbox`, `.pdf`, `.md` files. SHA-256 hash → skip if already in `documents.sha256` (dedup).
  - *AC:* Dropping the same file twice produces exactly 1 row in `documents`.

- **Story 1.2:** MBOX parser extracts `(sender_email, sender_name, recipients, subject, body_text, date)`. Each message → `documents` row + `persons` UPSERT. Malformed messages → `dead_letter`. **All DB writes (document + persons + outbox event) in a single transaction.**
  - *AC:* A 10 MB MBOX with 200 messages produces ≤ 200 `documents` rows within 60 s. Outbox has corresponding events.

- **Story 1.3:** PDF parser (`pdfminer.six`) and Markdown parser. Content-type: extension-first; `magika 1.0.1` fallback (`result.dl.ct_label`).
  - *AC:* A 5-page PDF and a headered Markdown file both produce non-empty `documents` rows.

- **Story 1.4:** Chunker: 512-token / overlap per Sprint 1 spike result. Each chunk → `chunks` row with `embedding_status='pending'` and `pii_detected` from PII scanner. BM25 available immediately via GIN index.
  - *AC:* `SELECT * FROM chunks WHERE tsv @@ to_tsquery('english', 'keyword')` returns results for a known keyword.

- **Story 1.5:** Embedding worker (`asyncio.Task`): UPDATE-with-RETURNING sets `embedding_status='processing'` atomically (prevents double-pick), calls Ollama batch (200 chunks), writes embedding + `embedding_status='done'`. On Ollama failure, increments `retry_count`; after `embed_retry_max` failures (config, default 5) sets `embedding_status='failed'` — prevents infinite loop on systematic Ollama errors (OOM, model not loaded). Failed chunks surfaced in TUI Dashboard error log. Heartbeat column shows "Xs ago"; alert at 120 s stall.
  - *AC:* After 200 chunks, `SELECT count(*) FROM chunks WHERE embedding_status='done'` = 200. p95 embed time documented. Simulated stall (pause Ollama) triggers TUI amber alert within 150 s. Simulated systematic Ollama failure (mock returning 500) results in chunks reaching `embedding_status='failed'` after 5 attempts, not looping indefinitely.

- **Story 1.6:** Outbox worker (`asyncio.Task`): polls `outbox WHERE processed_at IS NULL AND attempts < OUTBOX_MAX_ATTEMPTS`, applies events to FalkorDB, marks processed. After 10 failures, row marked dead (`processed_at='dead'`); surfaced in TUI Dashboard error log. FalkorDB schema changes that permanently break event processing are caught here.
  - *AC:* After ingest, FalkorDB has matching `:Person` and `:Document` nodes. Stopping `pkg-graph` and restarting results in outbox draining within 30 s. A mock event with an intentionally broken payload reaches `attempts=10` and stops retrying.

- **Story 1.7:** PII scanner runs during chunking: spaCy `PERSON` entity detection + regex patterns (SSN, credit card, medical terms). Sets `chunks.pii_detected=true` where triggered. Add `make scan-pii` Makefile target that runs the scanner over `WHERE pii_detected IS NULL` chunks for retroactive scanning of imported archives. Evaluate scanner accuracy against a labeled test set in `tests/pii_test_corpus/` (50 PII / 50 clean chunks).
  - *AC:* Test chunk with fake SSN (`123-45-6789`) → `pii_detected=true`. Clean chunk → `pii_detected=false`. `make scan-pii` processes all unscanned chunks and exits 0. Scanner precision > 90% and recall > 85% on labeled test corpus (documented in `docs/pii-eval.md`).

- **Story 1.8:** Vault sync: writes `./vault-sync/persons/` and `./vault-sync/documents/` Markdown with YAML frontmatter. Files created with `chmod 444` (read-only). Obsidian opens `./vault-sync/` as a vault.
  - *AC:* Opening `./vault-sync/` in Obsidian shows notes with correct frontmatter. `ls -l vault-sync/**/*.md` shows mode `444` on all files.

- **Story 1.9:** TUI Intake: file queue with per-file status, progress, and heartbeat column. TUI Search: BM25 query via `pkg-db`, results with filename and snippet. `E` opens in `$EDITOR`, `Enter` expands inline.
  - *AC:* Keyword search returns results in < 2 s. `E` key opens file (or prints path if `$EDITOR` unset).

- **Story 1.10:** Dead-letter retry: up to 3 times with backoff (2 s, 8 s, 32 s). TUI Dashboard shows error count.
  - *AC:* Corrupt file appears in TUI error log. Removing it and dropping a clean copy succeeds.

**Lean Metric:** Operator finds 5 specific known emails by keyword within 5 s each, at end of Sprint 2.

---

### Epic 2: Semantic Search & Hybrid Retrieval *(Sprints 3–4)*

**Goal:** Natural language queries work. Hybrid BM25 + vector search outperforms BM25 alone.

- **Story 2.1:** Hybrid search endpoint `POST /search` in `tui-controller` (FastAPI). Input validated by `SearchRequest(q: str = Field(max_length=2000), limit: int)`:
  1. Embed query with Ollama (`EMBED_MODEL` env var). If Ollama unreachable, **fall back to BM25-only** and include `"degraded": true` in response — no unhandled exception.
  2. BM25: `plainto_tsquery` → top 50.
  3. ANN: `embedding <=> $vec WHERE embedding_status='done'` → top 50 (skipped in BM25-fallback mode).
  4. RRF merge (`k` read from config table, default 60) → top 20.
  5. CrossEncoder rerank → top 10. Skip if result set < 5, reranker unavailable, or **top BM25 score > 0.95** (high-confidence shortcut). LRU cache on `(query_hash, frozenset(candidate_ids))` for repeated queries (TTL 60 s, max 128 entries).
  6. `slowapi` rate limiter: 100 requests/minute per IP (protects against Obsidian plugin hammering in Epic 3+).
  - *AC:* `curl -X POST localhost:8000/search -d '{"q":"budget meeting"}'` returns JSON with ≥ 1 result and `scores` object. A 10 001-character query returns HTTP 422. Hybrid Recall@5 > BM25-only Recall@5 on 500-email corpus. With Ollama container stopped, endpoint returns BM25-only results with `"degraded": true` (no 500 error). 101st request/minute returns HTTP 429.

- **Story 2.2:** TUI Search screen calls hybrid endpoint; renders BM25 score, vector score, and reranker score columns. Shows `[DEGRADED — BM25 only]` banner when `degraded: true` in response. Settings shows `rrf_k` as read-display alongside weights.
  - *AC:* Three numeric score columns visible. Degraded mode banner appears when Ollama is stopped. `rrf_k` visible in Settings.

- **Story 2.3:** Re-embedding (`make reindex`): re-embeds all chunks to `embedding_v2 VECTOR(N)` column via Alembic migration, then atomic rename. Admissible 5-minute window. Old column dropped after operator confirmation.

  > **Note:** During reindex, chunks temporarily have `embedding_status='pending'`. The partial HNSW index (`WHERE embedding_status='done'`) means those chunks drop out of ANN results — this is intentional and correct. BM25 continues to serve them during the window.

  - *AC:* After `make reindex`, search returns results from new model. Operator confirmation prompt shown before drop. BM25 remains functional throughout reindex window.

**Lean Metrics:** Recall@5 > 85%, MRR > 0.70, p95 query latency < 3 s — measured against `tests/corpus/`.

---

### Epic 3: Knowledge Graph & Entity Resolution *(Sprints 5–6)*

**Goal:** Connected graph of persons, documents, concepts. Wikilinks appear in Obsidian. MCP endpoint for Claude integration.

- **Story 3.1:** spaCy NER (`en_core_web_sm`, deterministic, no LLM in critical path) extracts `PERSON`, `ORG`, `GPE` entities. Each → `(:Concept)` node in FalkorDB via outbox. `valid_at` = ingest timestamp.
  - *AC:* `MATCH (c:Concept) RETURN count(c)` > 0 after 10 documents.

- **Story 3.2:** Entity resolution spike (Sprint 5, Day 1): run threshold sweep (0.80–0.99) against a labeled set of 50 known-duplicate and 50 known-distinct person pairs. Test **two scoring approaches**: (A) Jaro-Winkler on `display_name` only; (B) combined score = Jaro-Winkler + exact email domain match bonus + shared document count bonus. Plot precision/recall curves for both. Document which approach and threshold minimises false merges. Default 0.90 / string-only is provisional — spike result governs. Candidates at validated threshold surfaced in TUI Entities merge queue with expanded evidence row showing individual signal scores. Manual approval only — no auto-merge.
  - *AC:* Threshold and approach documented in `docs/entity-resolution-spike.md` with precision/recall curves for both strategies. Two known duplicates appear as candidates. Expanded evidence row shows Jaro-Winkler score, domain match, shared doc count individually. No merge without operator action.

- **Story 3.3:** Canary guard: `tests/canary_pairs.json` lists known-distinct pairs. After every resolution run, assert none share a `merged_into` chain. Alert in TUI Dashboard if violated.
  - *AC:* Deliberately merging a canary pair triggers dashboard alert within the next run.

- **Story 3.4:** Obsidian Wikilinks: vault sync writes `[[Person/Alice]]` links in document notes from FalkorDB `:MENTIONS` edges.
  - *AC:* Document note in Obsidian shows `[[Person/...]]` links for each mentioned person.

- **Story 3.5:** MCP server endpoint: `tui-controller` exposes `/mcp/` (MCP Python SDK, HTTP/SSE). Tools: `add_document(text, metadata)`, `search_facts(query)`, `search_nodes(label, property_filter)`.
  - *AC:* Claude Desktop config pointing to `http://localhost:8000/mcp/` calls `search_facts("budget meeting")` and returns results from `pkg-db`.

**Lean Metric:** Entity resolution precision > 99% on canary set across 3 consecutive runs.

---

### Epic 4: Bi-directional Sync, Auth & Privacy Hardening *(Sprints 7–8)*

**Goal:** Obsidian can write back. Deletion is safe. Auth is appropriate for a local system.

- **Story 4.1:** Obsidian plugin (TypeScript, BRAT) calls `PUT /entity/{id}` with frontmatter diffs. Conflict rule: server timestamp wins; flagged in TUI.
  - *AC:* Editing a tag in Obsidian frontmatter propagates to `documents.metadata` within 10 s. Vault-sync files become writable (`chmod 644`) only after this story ships.

- **Story 4.2:** Auth: single scoped API key per service (read-only for Obsidian plugin, read-write for `ingest-worker`). Keys via Docker secrets or `.env`. `make rotate-keys`. No JWTs.
  - *AC:* Invalid key → HTTP 401. Read-only key on write endpoint → HTTP 403.

- **Story 4.3a — Soft delete:** `DELETE /entity/{id}` sets `deleted_at = now()` on `documents`/`persons`. Entity is excluded from search immediately (add `WHERE deleted_at IS NULL` to all queries). FalkorDB edges get `invalid_at` set via outbox event. TUI shows confirmation modal with entity summary before action.
  - *AC:* Soft-deleted entity not returned in search. Confirmation modal shown. `deleted_at` populated in DB.

- **Story 4.3b — Hard delete (30-day gate):** `make hard-delete --confirm` finds all soft-deleted rows with `deleted_at < now() - interval '30 days'`. Cascades: `DELETE FROM documents` (chunks cascade via FK) + FalkorDB `DETACH DELETE` via outbox. Appends receipt to `./data/deletion_log.jsonl`.

  > **Note on JSONB outbox references:** The `outbox` table stores person and document IDs in JSONB `payload` fields. These are point-in-time snapshots, not FK references — Postgres does not cascade deletes into JSONB. After hard-deleting a person, any unprocessed outbox rows referencing that person ID will produce a benign FalkorDB "node not found" error, increment their `attempts` counter, and eventually dead-letter. This is acceptable: the node is already gone from FalkorDB. No data integrity issue — cosmetic noise in the dead-letter log only.

  - *AC:* Entity older than 30 days in quarantine is permanently removed. Receipt file contains SHA-256 of payload + timestamp. Entity with `deleted_at` < 30 days ago is NOT deleted.

- **Story 4.4:** PII report: TUI Settings → "PII Report" lists `persons (pii=true)` with document counts, **plus** `chunks (pii_detected=true)` count per document. Operator can mark a person `pii=false` (public figure) to exclude from report. Operator can bulk-redact PII-flagged chunks (replaces text with `[REDACTED]`).
  - *AC:* PII report shows both person-level and chunk-level PII. Marking `pii=false` removes person from list. Redaction replaces chunk text and clears `embedding` (forces re-embed with redacted text).

- **Story 4.5:** Search weight configuration: TUI Settings exposes BM25/vector sliders (0.0–1.0, sum = 1.0). Writes to `config` table. `/search` endpoint reads at query time and applies **weighted score fusion** (BM25_score × w1 + ANN_score × w2) instead of pure RRF when weights differ from 0.5/0.5.
  - *AC:* BM25 weight = 1.0 → results identical to pure BM25 baseline. Vector weight = 1.0 → results identical to pure ANN baseline.

- **Story 4.6:** Prometheus metrics (deferred from Sprint 0, YAGNI): `/metrics` on port 9090. Metrics: `pkg_chunks_total`, `pkg_ingest_latency_seconds`, `pkg_query_latency_seconds`, `pkg_outbox_depth` (queue depth). Optional scrape target.
  - *AC:* `curl localhost:9090/metrics` returns valid Prometheus text format.

---

## 7. Non-Functional Requirements

| Concern | Requirement |
|---------|-------------|
| **Privacy** | No data leaves the host. All inference runs locally via Ollama. No telemetry. Vault-sync files read-only (`chmod 444`) until Epic 4 write-back. |
| **Storage** | All persistent data in named Docker volumes. `make backup` tarballs all volumes daily (cron). `make storage-report` prints per-table row counts, pg_size_pretty, total vector storage (chunks × 3 KB per VECTOR(768)), and projected growth rate. Archival trigger: >500K chunks (~1.5 GB vectors) — see Out of Scope. |
| **Portability** | Runs on macOS Apple Silicon (`linux/arm64`) and Linux x86-64 (`linux/amd64`). All pinned images publish both platforms. |
| **Resilience** | `dead_letter` for parse failures. `outbox` for cross-service consistency. `embedding_status` enum prevents race conditions. `FOR UPDATE SKIP LOCKED` prevents double-claim. `INGEST_SEMAPHORE(10)` limits concurrent ingest tasks. Bounded `asyncio.Queue(maxsize=500)` for embedding backpressure. |
| **Observability** | Structured JSON logs (see §7.1 below). `make logs` tails them. TUI heartbeat column per file. Outbox depth + embedding queue depth on Dashboard. Prometheus metrics in Epic 4. |
| **Upgradability** | All images pinned to exact versions. `make upgrade` bumps and runs `make test`. pgvector major version bumps require `REINDEX TABLE chunks` — see Open Decisions. |
| **Data Safety** | Soft-delete (30-day quarantine) before hard-delete. Two-keystroke confirmation on any destructive action. `./data/deletion_log.jsonl` receipt file. |
| **Connection Pooling** | Both `ingest-worker` and `tui-controller` use `psycopg_pool.AsyncConnectionPool(min_size=2, max_size=5)`. Prevents connection exhaustion under Ollama stalls or search load. |

### 7.1 Log Event Schema

All services emit newline-delimited JSON. Minimum required fields:

```json
{
  "timestamp": "2026-02-24T10:31:00.123Z",
  "service":   "ingest-worker",
  "level":     "info",
  "event":     "chunk_embedded",
  "chunk_id":  "uuid",
  "doc_id":    "uuid",
  "latency_ms": 142
}
```

`level` values: `debug`, `info`, `warning`, `error`. `event` is a stable snake_case identifier (not a free-form message) — makes log parsing deterministic. Use `structlog` or `python-json-logger` in both services.

### 7.2 Hardware Requirements

Minimum and recommended specs for running the full 4-service stack:

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 12 GB | 16 GB+ |
| CPU | 4 cores | 8 cores (M-series or Zen 4+) |
| Disk | 20 GB SSD | 50 GB SSD |
| OS | macOS 13+ or Ubuntu 22.04+ | macOS 14+ (Apple Silicon) or Ubuntu 24.04 |

**Memory breakdown (peak):**
- Ollama + `nomic-embed-text`: ~4–6 GB
- `tui-controller` + CrossEncoder: ~850 MB
- `ingest-worker` + spaCy: ~600 MB
- Postgres 17 + pgvector (shared_buffers default): ~256 MB
- FalkorDB: ~200 MB
- **Total: ~6–8 GB active, 12 GB comfortable, 16 GB headroom for large batches**

> On 8 GB machines: use `all-minilm` (`EMBED_MODEL=all-minilm`, ~1 GB) instead of `nomic-embed-text`. Disable CrossEncoder reranking (`RERANKER_ENABLED=false`). This reduces RAM to ~3–4 GB at the cost of search quality.

### 7.3 Disaster Recovery

**RPO (Recovery Point Objective):** Up to 24 hours of ingestion may be lost. Re-ingesting from `./drop-zone/` is always possible since source files are not deleted.

**RTO (Recovery Time Objective):** Target < 30 minutes from backup to operational system.

**Restore runbook:**
```bash
# 1. Stop all services
make down

# 2. Restore volumes from backup tarball
make restore-from-backup BACKUP=./backups/pkg-backup-2026-02-24.tar.gz

# 3. Restart and verify health
make up
docker compose ps   # all 4 services healthy
make sanity         # orphaned chunks = 0

# 4. Run pending Alembic migrations (if restoring to new version)
make migrate-up
```

**Backup frequency:** Daily via cron. Recommended crontab entry:
```
0 3 * * * cd /path/to/pkg && make backup >> /var/log/pkg-backup.log 2>&1
```

### 7.4 Unattended Monitoring

`make healthcheck` target: runs `docker compose ps --format json` and checks all 4 services are `healthy`. On failure, writes to `./data/health.log` and sends a macOS notification via `osascript` (Linux: `notify-send`). Intended as a cron job:

```
*/15 * * * * cd /path/to/pkg && make healthcheck
```

No Prometheus or external alerting required for solo operator use.

---

## 8. Agile Rituals & CI

**Sprint cadence:** 2-week sprints. Each sprint delivers a working vertical slice demonstrated against real personal data.

**Definition of Done (system-wide):** (a) works end-to-end in Docker stack, (b) reachable from TUI or vault sync, (c) acceptance criteria pass in `make test`.

**Continuous Integration (`make test`):**
- Parser unit tests (MBOX, PDF, Markdown)
- Dedup test (same file twice → 1 document row)
- Outbox convergence test (stop FalkorDB mid-ingest, restart, assert graph catches up)
- Outbox dead-letter test (mock permanent FalkorDB failure → row reaches `attempts=10`, stops retrying)
- Embedding status state machine test (pending → processing → done; systematic failure → failed after 5 attempts)
- Ollama-down search fallback test (stop Ollama, assert `/search` returns BM25-only with `degraded: true`, no 500)
- Canary entity resolution check
- Hybrid search Recall@5 + MRR against `tests/corpus/` (Sprint 4+)
- PII scanner unit tests + precision/recall against `tests/pii_test_corpus/` (Sprint 2+)
- Docker health checks for all 4 services
- `make sanity` (orphaned chunk count = 0)
- `make test-backup-restore` (backup/restore cycle with seeded data, assert row counts match)
- Alembic: `make migrate-up` exits 0 on clean DB (no pending migrations)

**Feedback loop:** Weekly self-usage session with a structured format: (1) three specific tasks performed (e.g. "find email about X", "merge duplicate contact", "check ingest status"), (2) time-on-task noted, (3) friction points written down as one-line observations. If two consecutive weeks produce the same friction note, it becomes a story in the next sprint. If TUI friction causes skipped ingestion, pivot to UX before adding parsers or models.

---

## 9. File & Folder Structure

```
./
├── docker-compose.yml
├── docker-compose.override.yml   # local dev: exposed ports
├── Makefile
├── .env.example                  # EMBED_MODEL, POSTGRES_PASSWORD, PKG_API_KEY_RW, PKG_API_KEY_RO
├── .gitignore                    # *.db, data/, .env, vault-sync/
├── drop-zone/                    # host bind mount — intake files dropped here
├── vault-sync/                   # host bind mount — Obsidian reads; files are chmod 444
├── services/
│   ├── ingest-worker/
│   │   ├── Dockerfile
│   │   ├── main.py               # asyncio entry: starts watch_loop, embedding_worker, outbox_worker
│   │   ├── watcher.py            # watchfiles ExtFilter + ingest pipeline
│   │   ├── detect.py             # ext-first + magika 1.0.1 fallback
│   │   ├── parsers/
│   │   │   ├── mbox.py
│   │   │   ├── pdf.py
│   │   │   └── markdown.py
│   │   ├── chunker.py            # 512-token / overlap (from spike)
│   │   ├── pii_scanner.py        # spaCy + regex; returns bool per chunk
│   │   ├── embedder.py           # Ollama client, batch 200, asyncio.Queue
│   │   ├── outbox_worker.py      # drains outbox → FalkorDB
│   │   ├── graph_writer.py       # FalkorDB apply_outbox_event() (SENT + RECEIVED edges)
│   │   └── vault_sync.py         # writes ./vault-sync/ Markdown (chmod 444)
│   ├── tui-controller/
│   │   ├── Dockerfile
│   │   ├── api/
│   │   │   ├── main.py           # FastAPI app
│   │   │   ├── search.py         # POST /search (SearchRequest + RRF + rerank)
│   │   │   └── mcp.py            # /mcp/ MCP server (Epic 3)
│   │   └── tui/
│   │       ├── app.py            # Textual 8.x App + BINDINGS
│   │       └── screens/
│   │           ├── welcome.py     # first-run screen (empty documents table)
│   │           ├── dashboard.py
│   │           ├── intake.py      # heartbeat column, stall alert, action microcopy footer
│   │           ├── search.py      # E=obsidian URI or $EDITOR, O/Enter bindings, score columns
│   │           ├── entities.py    # merge queue with evidence expansion
│   │           ├── graph.py       # Textual Tree widget + X=Vis.js export
│   │           ├── graph_export.py  # render_visjs() → self-contained graph.html
│   │           ├── settings.py    # read-display config values from config table
│   │           └── help.py        # ModalScreen key-binding overlay
│   └── db-init/
│       ├── init.sql
│       └── alembic/              # Alembic migration environment
│           ├── alembic.ini
│           ├── env.py
│           └── versions/         # migration files (e.g. 001_initial.py, 002_embedding_v2.py)
├── data/                         # gitignored
│   ├── postgres/
│   ├── falkordb/
│   ├── ingest/
│   └── deletion_log.jsonl        # hard-delete receipts
├── docs/
│   ├── perf-spike.md             # Sprint 1 embedding + overlap results
│   └── entity-resolution-spike.md  # Sprint 5 threshold sweep results
└── tests/
    ├── corpus/                   # 500-email anonymised eval set
    ├── canary_pairs.json
    ├── eval_ir.py                # Recall@5, MRR
    ├── test_pii_scanner.py
    ├── test_outbox.py            # convergence test
    └── test_embedding_states.py  # state machine test
```

---

## 10. docker-compose.yml (Reference)

```yaml
# docker-compose.yml — all images pinned

services:

  pkg-db:
    image: pgvector/pgvector:0.8.1-pg17
    container_name: pkg-db
    restart: unless-stopped
    environment:
      POSTGRES_DB:       pkg
      POSTGRES_USER:     pkg
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pkg_postgres:/var/lib/postgresql/data
      - ./services/db-init/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pkg -d pkg"]
      interval: 10s
      timeout: 5s
      retries: 5
    user: "70:70"
    # 70:70 is the postgres user inside the pgvector image — owns pkg_postgres named volume only.
    # No conflict with ingest-worker/tui-controller (1000:1000): those services mount
    # ./drop-zone and ./vault-sync bind mounts, not the postgres data volume.

  pkg-graph:
    image: falkordb/falkordb:v4.14.9
    container_name: pkg-graph
    restart: unless-stopped
    volumes:
      - pkg_falkordb:/data
      # FalkorDB (Redis-based) persists to /data inside the container.
      # /var/lib/falkordb/data is incorrect and would cause silent data loss on restart.
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  ollama:
    image: ollama/ollama:0.9.0
    container_name: pkg-ollama
    restart: unless-stopped
    volumes:
      - pkg_ollama:/root/.ollama
    # GPU: uncomment if NVIDIA available
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]
    healthcheck:
      test: ["CMD-SHELL", "curl -fs http://localhost:11434/api/version || exit 1"]
      interval: 15s
      timeout: 10s
      retries: 5

  ingest-worker:
    build: ./services/ingest-worker
    container_name: pkg-ingest
    restart: unless-stopped
    depends_on:
      pkg-db:    {condition: service_healthy}
      pkg-graph: {condition: service_healthy}
      ollama:    {condition: service_healthy}
    environment:
      DATABASE_URL:   postgresql://pkg:${POSTGRES_PASSWORD}@pkg-db:5432/pkg
      FALKORDB_HOST:  pkg-graph
      FALKORDB_PORT:  "6379"
      OLLAMA_URL:     http://ollama:11434
      EMBED_MODEL:    nomic-embed-text
      PKG_API_KEY:    ${PKG_API_KEY_RW}
    volumes:
      - ./drop-zone:/drop-zone:ro
      - ./vault-sync:/vault-sync
      - pkg_ingest:/data
    user: "1000:1000"

  tui-controller:
    build: ./services/tui-controller
    container_name: pkg-tui
    restart: unless-stopped
    tty: true
    depends_on:
      pkg-db:    {condition: service_healthy}
      pkg-graph: {condition: service_healthy}
    environment:
      DATABASE_URL:    postgresql://pkg:${POSTGRES_PASSWORD}@pkg-db:5432/pkg
      FALKORDB_HOST:   pkg-graph
      FALKORDB_PORT:   "6379"
      OLLAMA_URL:      http://ollama:11434
      EMBED_MODEL:     nomic-embed-text
      PKG_API_KEY_RW:  ${PKG_API_KEY_RW}
      PKG_API_KEY_RO:  ${PKG_API_KEY_RO}
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      - ./vault-sync:/vault-sync:ro
    user: "1000:1000"

volumes:
  pkg_postgres:
  pkg_falkordb:
  pkg_ollama:
  pkg_ingest:
```

---

## 11. Open Decisions (Minimal)

| Question | Decision | When |
|----------|----------|------|
| Embedding model if `nomic-embed-text` too slow | Switch to `all-minilm` via `EMBED_MODEL` env var; on 8 GB machines also set `RERANKER_ENABLED=false` | Sprint 1 spike result |
| Chunk overlap (25 / 50 / 100 tokens) | A/B tested in Sprint 1 spike; value baked into `config` table | Sprint 1 spike result |
| Jaro-Winkler threshold | Threshold sweep in Sprint 5 spike; documented in `docs/entity-resolution-spike.md` | Sprint 5 |
| Obsidian plugin distribution | BRAT for development; community submission after Epic 4 | End of Epic 4 |
| LLM enrichment (optional) | Ollama `llama3.2` for concept extraction; off by default (`ENABLE_LLM_ENRICHMENT=false`) | Epic 3 review |
| Weighted fusion vs. RRF | RRF in Epics 1–3; weighted score fusion only if Sprint 4 empirical test shows meaningful gain | Sprint 4 evaluation |
| pgvector minor version bumps | HNSW indexes survive minor bumps. **Major version bumps** (e.g. 0.8 → 1.0) may require `REINDEX TABLE chunks` — run `make migrate-up` which includes a post-migration REINDEX step if the Alembic migration declares one | At upgrade time |
| Search result cache during ingestion | LRU cache (60 s TTL, configurable via `search_cache_ttl` in config table) may serve stale results during active ingestion. Set `search_cache_ttl=0` to disable. Accepted trade-off for solo operator | Operator preference |

---

## 12. Out of Scope (YAGNI)

- Web admin panel
- Multi-user / shared access
- Cloud sync or off-device backup
- LLM-generated summaries in the ingest critical path
- External job queue service (Celery, Redis Queue, Dramatiq) — bounded `asyncio.Queue` + outbox covers the use case
- Prometheus alerting rules or Grafana dashboards
- Kubernetes deployment
- Vector archival / cold storage (relevant trigger: >500K chunks / ~1.5 GB vector data — run `make storage-report` to monitor; archival strategy TBD at that scale)
