# Peanut — Personal Knowledge Graph System

## Project Overview

A self-hosted, containerised personal knowledge system that transforms raw personal data
(emails, documents, PDFs, notes) into a queryable semantic knowledge graph, surfaced
through a Textual TUI and Obsidian.

Full requirements: `knowledge-base-prd-v3.2_1.md`

## Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.12 |
| TUI | Textual 8.x |
| API | FastAPI |
| DB | Postgres 17 + pgvector 0.8.1 |
| Graph | FalkorDB v4.14.9 (Redis-based) |
| Embeddings | Ollama `nomic-embed-text` — **runs on host, NOT in Docker** |
| Reranker | sentence-transformers CrossEncoder (in-process in tui-controller) |
| Migrations | Alembic |
| Testing | pytest + pytest-asyncio |
| Lint | ruff |
| Containers | Docker Compose |

## Critical Architecture Rules

- **Ollama is on the host.** Connect via `host.docker.internal:11434` (Mac/Windows) or
  `172.17.0.1:11434` (Linux). Never add an `ollama` service to docker-compose.yml.
- **All schema changes via Alembic.** Never hand-edit a running schema. Always `make migrate-up`.
- **Outbox pattern for FalkorDB.** Never write to FalkorDB directly from the ingest path.
  All graph writes go through the `outbox` table → outbox worker → FalkorDB.
- **Single Postgres transaction per ingest event**: document + persons UPSERT + outbox INSERT
  must be atomic. Never split across commits.
- **FOR UPDATE SKIP LOCKED** in the embedding worker. Prevents double-pick if container restarts.
- **No auto-merge in entity resolution.** Human must press M + confirm.

## Source Layout

```
src/
  ingest/       # ingest-worker service (watchfiles, parsers, chunker, workers)
  tui/          # tui-controller: Textual app + FastAPI REST
  api/          # FastAPI routes (search.py, entities.py, mcp.py)
  shared/       # shared utilities (db pool, config reader, pii scanner)
db/
  init.sql      # bootstrap schema (run once on container start)
  migrations/   # Alembic migration files — all schema changes go here
tests/
  harness/      # harness gap cases (production regression → add case here first)
  pii_test_corpus/  # 50 PII + 50 clean chunks for scanner accuracy validation
  canary_pairs.json # known-distinct person pairs; asserts no merged_into chain
docker-compose.yml
Makefile
risk-policy.json
```

## Conventions

### Code Quality
- **Lint:** `ruff check src/ tests/` — must pass before commit
- **Types:** `mypy src/` for critical modules (ingest workers, API routes)
- **Test before commit:** `pytest tests/ --tb=short -q` must be green
- **Small commits:** One story per PR. Prefix: `feat:`, `fix:`, `test:`, `refactor:`, `chore:`

### Testing
- Tests mirror `src/` in `tests/`
- Worker tests use `pytest-asyncio` with `asyncio_mode = "auto"`
- Database tests use a test Postgres instance (see `docker-compose.test.yml`)
- **Harness gap rule:** If fixing a production regression, add `tests/harness/<issue>.py` FIRST

### PR Checklist (before marking any task done)
- [ ] Acceptance criteria in `tasks.md` met
- [ ] `ruff check` passes
- [ ] `pytest` passes (including harness tests)
- [ ] `risk-policy.json` updated if new high-risk paths added
- [ ] `PRD.md` link added if API/schema changed
- [ ] No hardcoded secrets; no Ollama URL hardcoded — use env var `OLLAMA_URL`

### Key Environment Variables
```
POSTGRES_URL        postgresql://user:pass@pkg-db:5432/pkg
FALKORDB_HOST       pkg-graph
FALKORDB_PORT       6379
OLLAMA_URL     http://host.docker.internal:11434  # host Ollama
VAULT_SYNC_PATH     ./vault-sync
DROP_ZONE_PATH      ./drop-zone
```

### Makefile Targets
```
make up                   # docker compose up -d
make down                 # docker compose down
make reset                # down -v + up (wipes volumes)
make logs                 # docker compose logs -f
make tui                  # docker exec -it pkg-tui python tui/app.py
make migrate-up           # alembic upgrade head
make backup               # pg_dump to ./data/backups/
make restore-from-backup  # restore latest backup
make test-backup-restore  # full backup/restore cycle with row count assertion
make sanity               # check for orphaned chunks
make audit                # trivy image scan
make hard-delete          # requires --confirm; 30-day quarantine gate
make scan-pii             # run PII scanner over WHERE pii_detected IS NULL
make reindex              # re-embed all chunks to embedding_v2 (Story 2.3)
```
