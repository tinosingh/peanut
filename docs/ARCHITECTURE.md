# Peanut Architecture & Design Decisions

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Textual TUI                              │
│  (Dashboard, Search, Entities, Graph, Settings screens)    │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI REST API (localhost:8000)              │
│  /search /entities/merge /config /metrics /health           │
└──────────────────┬──────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┬──────────────┐
        │                     │              │
        ▼                     ▼              ▼
   ┌────────┐          ┌──────────┐   ┌──────────┐
   │Postgres│          │FalkorDB  │   │  Ollama  │
   │+ pgvec │          │ (Redis)  │   │ (Host)   │
   └────────┘          └──────────┘   └──────────┘
        ▲
        │
        └─── ingest-worker (watcher, parsers, workers)
```

---

## Architectural Patterns

### 1. Outbox Pattern (Transactional Outbox)

**Problem:** Postgres and FalkorDB must stay in sync, but they're separate systems.

**Solution:** All graph writes go through an `outbox` table in Postgres.

```
Ingest Flow:
  1. User drops email.mbox → watcher detects
  2. Parse email → extract sender, recipients
  3. BEGIN TRANSACTION
     - INSERT documents row
     - INSERT persons rows
     - INSERT chunks rows
     - INSERT outbox event (type=document_added)
  4. COMMIT (atomic)
  5. outbox_worker continuously polls outbox
  6. Applies event to FalkorDB
  7. Updates outbox.processed_at = now()
```

**Benefits:**
- Single source of truth: Postgres
- FalkorDB is a derived cache
- If FalkorDB fails, events queue up
- No lost writes to graph

**Guarantees:**
- At-least-once delivery (retried up to 10 times)
- Dead-letter queue for unprocesable events (outbox.failed=true)

---

### 2. Entity Resolution via Outbox

When user merges two persons via UI:
1. Server updates `persons.merged_into = id_a` for person B
2. Inserts `person_merged` outbox event with {merged_from, merged_into}
3. outbox_worker applies to FalkorDB (marks old edges as invalid_at)
4. Canary guard checks if known-distinct pairs share merged_into chain

---

### 3. Embedding Pipeline with Retry Logic

**Flow:**
```
embedding_worker (async loop):
  1. Poll chunks WHERE embedding_status='pending'
  2. FOR UPDATE SKIP LOCKED (safe concurrent operation)
  3. UPDATE status to 'processing'
  4. Batch call to Ollama /api/embed
  5. On success: UPDATE chunks SET embedding=..., status='done'
  6. On failure:
     - Increment retry_count
     - If retry_count >= 5: status='failed'
     - Else: status='pending' for next poll
```

**Why separate worker?**
- Ollama runs on host (not in Docker)
- Can be restarted independently
- Batching improves throughput
- Long timeouts (120s) don't block API

---

### 4. Search: BM25 + ANN + RRF + CrossEncoder

**Pipeline:**
```
User query "project budget"
  │
  ├─→ BM25 (PostgreSQL tsvector + pg_trgm)
  │   └─→ Top 50 by full-text match
  │
  ├─→ ANN (pgvector cosine similarity)
  │   ├─→ Embed query with Ollama
  │   └─→ Top 50 by vector similarity
  │
  ├─→ RRF Merge (Reciprocal Rank Fusion)
  │   └─→ Combines BM25 + ANN rankings
  │
  └─→ CrossEncoder Rerank
      ├─→ Fine-tuned semantic reranker
      └─→ Final top-K by relevance
```

**Degradation:**
- If Ollama down → BM25 only (degraded=true)
- If CrossEncoder unavailable → RRF scores (degraded=true)

---

### 5. Entity Resolution Scoring

**score_pair_b = 0.6 × name_sim + 0.3 × domain_match + 0.1 × shared_docs**

- **name_sim:** Jaro-Winkler distance (0-1)
- **domain_match:** 1.0 if same email domain, else 0.0
- **shared_docs:** min(count/5, 1.0) for documents both appear in

**Production threshold:** 0.90 (only merges with high confidence + shared docs signal)

**Why email domain?** Email domain is often fixed (company domain), so matching domains strongly indicates same person.

---

### 6. Vault Sync (Obsidian Integration)

Two-way sync with Obsidian via PUT /entities:

**On ingest:**
- Creates markdown files in `./vault-sync/documents/` and `./vault-sync/persons/`
- Encodes doc_id and person_id as unique suffix

**On merge:**
- Calls update_document_wikilinks() to append a ## Mentions section with [[wikilinks]]

**Conflict resolution:**
- Client timestamp vs server timestamp
- Server timestamp always wins (simpler than 3-way merge)

---

### 7. Watcher & File Processing

**Pattern: Atomic ingest with deduplication**

```
Watcher (watchfiles):
  1. Detects new file in drop-zone/
  2. Computes SHA-256
  3. Checks if seen before (dedup)
  4. Passes to handle_file()
  
Pause sentinel:
  - Create `drop-zone/.pause` file to pause watcher
  - No new files processed while paused
  - Used for maintenance/manual intervention
```

---

## Data Flow Diagram

```
┌────────────┐
│ Drop Zone  │ (user copies files)
└─────┬──────┘
      │
      ▼
┌──────────────────┐
│ Watcher          │ (detects new files)
└─────┬────────────┘
      │
      ▼
┌──────────────────┐      ┌─────────────┐
│ Parser           │◄────►│ Chunker     │
│ (detect type)    │      │ (text split)│
└─────┬────────────┘      └─────────────┘
      │
      ▼
┌──────────────────┐      ┌──────────────┐
│ PII Scanner      │◄────►│ Embedding    │
│ (NER + regex)    │      │ Queue        │
└─────┬────────────┘      └──────────────┘
      │
      ▼
┌─────────────────────────────────────┐
│ Single Transaction:                 │
│  INSERT documents                   │
│  INSERT persons (senders/recipients)│
│  INSERT chunks                      │
│  INSERT outbox event                │
│  COMMIT (atomic)                    │
└─────┬───────────────────────────────┘
      │
      ├─→ ┌──────────────────┐
      │   │ Embedding Worker │◄──┐
      │   │ (Ollama polling) │   │ Retry loop
      │   └────────┬─────────┘   │
      │            │             │
      │            ▼             │
      │   ┌──────────────────┐   │
      │   │ UPDATE chunks    ├───┘
      │   │ SET embedding    │
      │   └──────────────────┘
      │
      └─→ ┌──────────────────┐
          │ Outbox Worker    │
          │ (FalkorDB sync)  │
          └────────┬─────────┘
                   │
                   ▼
          ┌──────────────────┐
          │ FalkorDB Graph   │
          │ CREATE nodes     │
          │ CREATE edges     │
          └──────────────────┘
```

---

## Critical Design Decisions

### Why Outbox Pattern?

**Alternative: Direct sync to FalkorDB**
- Risk: Network fails, FalkorDB down → ingest incomplete
- Outbox: Postgres is transactional, FalkorDB is eventual-consistent

**Why not queue (RabbitMQ, Redis)?**
- Outbox is simpler, single table in Postgres
- Works offline if needed

---

### Why pgvector + FalkorDB (two databases)?

**pgvector:** Normalized chunks with embeddings
- Searchable via SQL WHERE clauses
- Cost-effective storage
- Easy to filter by date, source, PII flag

**FalkorDB:** Graph relationships (Person → Document → Concept)
- Natural representation of mentions
- Enables "find documents mentioning X and Y together"
- Temporal edges (valid_at, invalid_at for merges)

---

### Why RRF instead of simple score averaging?

**Problem:** BM25 and vector scores are on different scales.
- BM25: unbounded (typically 0-50)
- Cosine: 0-1

**Solution: RRF (Reciprocal Rank Fusion)**
- Converts both to ranks (position in result list)
- Fuses as: 1/(k+rank1) + 1/(k+rank2)
- Works with any ranking system

**Weighted alternative:** If weights configured, uses min-max normalization:
- score_normalized = (x - min) / (max - min)
- final = w1×bm25_norm + w2×vector_norm

---

### Why CrossEncoder for reranking?

**Problem:** Search results need semantic relevance, not just keyword/vector matching.

**Bi-Encoder (CLIP, Sentence-BERT):**
- Fast: Query encoded once, compared to pre-encoded docs
- But: Doesn't see query+doc together, misses interaction signals

**CrossEncoder (MSMarco):**
- Slow: Query+doc encoded as pair
- But: Captures interaction ("does doc actually answer query?")
- Used as final rerank step (top-K only, not all docs)

---

## Security Considerations

1. **No Authentication:** Assumes localhost or private network
2. **SQL Injection:** All queries parameterized (psycopg3 positional)
3. **XSS in Graph Export:** JSON escaped in HTML template
4. **PII Detection:** Two-pass (regex fast, NER fallback)
5. **Secrets:** No hardcoded; env vars only (OLLAMA_URL, FALKORDB_HOST)
6. **Rate Limiting:** 100 req/min per IP via slowapi

---

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Ingest email | 2-5s | Parse + PII scan + chunk |
| Embed batch (200) | 1-3s | Ollama latency |
| Search query | 100-500ms | BM25 + ANN + RRF + rerank |
| Graph export | <100ms | Cypher query + Vis.js render |
| Entity merge | 10-50ms | FK update + outbox event |

---

## Testing Strategy

1. **Unit tests:** Worker logic, scoring, chunking (no DB)
2. **Integration tests:** Full pipeline with test Postgres (Docker)
3. **Harness tests:** Production regression cases
4. **E2E test:** Full Docker Compose stack (manual)

---

## Deployment Notes

- **Ollama:** Host-only, not in Docker
- **Postgres/FalkorDB:** docker-compose services
- **Env vars:** See CLAUDE.md for full list
- **Migrations:** Alembic for schema changes (never hand-edit)
- **Backups:** `make backup` uses pg_dump
