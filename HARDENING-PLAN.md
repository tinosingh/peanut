# Stack Hardening Plan — 24 Reliability Fixes

## Phase 1 — Data Integrity (CRITICAL)

- [x] 1. Move chunk insertion into `ingest_document()` transaction (`src/ingest/db.py`) — atomic doc+chunks+outbox
- [x] 2. Fix outbox worker: mark processed BEFORE applying to FalkorDB, rollback on failure (`src/ingest/outbox_worker.py`)
- [x] 3. Add FalkorDB connection retry with exponential backoff at startup (`src/ingest/outbox_worker.py`)
- [x] 4. Add pool shutdown handler in FastAPI (`src/tui/main.py`)
- [x] 5. Make `/health` actually check DB + Ollama connectivity (`src/tui/main.py`)
- [x] 6. Log ERROR when spaCy model missing instead of silent warning (`src/ingest/pii.py`)

## Phase 2 — Resilience (HIGH)

- [x] 7. Graceful shutdown with 10s timeout in ingest main (`src/ingest/main.py`)
- [x] 8. Batch embedding UPDATEs via executemany (`src/ingest/embedding_worker.py`)
- [x] 9. Add PII endpoints to `_WRITE_PATHS` in auth (`src/api/auth.py`)
- [x] 10. Thread-safe bounded search cache with lock (`src/api/search.py`)
- [x] 11. Atomic vault sync via temp-file + os.replace (`src/ingest/vault_sync.py`)
- [x] 12. Docker resource limits for all services (`docker-compose.yml`)
- [x] 13. Increase connection pool max_size from 5 to 15 (`src/shared/db.py`)
- [x] 14. Circuit breaker for embedding worker (10 errors → 60s backoff) (`src/ingest/embedding_worker.py`)
- [x] 15. Add missing DB indexes: `chunks_pii_idx`, `outbox_drain_idx` (`db/init.sql`)

## Phase 3 — Hardening (MEDIUM)

- [x] 16. Graph init container `restart: on-failure` (`docker-compose.yml`)
- [x] 17. Batch outbox graph queries into single Cypher query (sender + recipients) (`src/ingest/outbox_worker.py`)
- [x] 18. Config validation bounds: chunk_size >= 1, overlap < chunk_size (`src/ingest/main.py`)
- [x] 19. Upper bound version pins in dependencies (`pyproject.toml`)
- [x] 20. Remove dead `EMBED_QUEUE` code (`src/ingest/embedding_worker.py`)
- [x] 21. Add `FOR UPDATE` lock on merge endpoint (`src/api/entities.py`)
- [x] 22. Sanitize DB error text in metrics response — only expose error type name (`src/api/metrics.py`)
- [x] 23. Run `sha256_file()` in thread pool executor (`src/ingest/watcher.py`)
- [x] 24. Add LIMIT/pagination to bulk redact with configurable batch_size (`src/api/config_api.py`)

## Validation

- 322 tests passing, 9 skipped
- ruff clean
- All 24 fixes implemented and verified
