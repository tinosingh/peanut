## PEANUT

A self-hosted, containerised personal knowledge system that transforms raw personal data
(emails, documents, PDFs, notes) into a queryable semantic knowledge graph.

Drop files in. Search everything. Graph your connections.

---

## What it does

- **Ingest** `.mbox`, `.pdf`, `.md`, and `.txt` files from a watch folder
- **Chunk & embed** content using Ollama (`nomic-embed-text`) running on your host
- **Hybrid search** — BM25 + vector ANN + CrossEncoder reranking in one query
- **Knowledge graph** — extracts persons, documents, and concepts into FalkorDB
- **PII detection** — flags and optionally redacts personal information
- **Entity resolution** — Jaro-Winkler scoring + manual merge confirmation
- **TUI** — full-featured Textual terminal interface with live ingest monitoring

---

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| TUI | Textual 8.x |
| API | FastAPI + slowapi |
| Database | PostgreSQL 17 + pgvector 0.8.1 |
| Graph | FalkorDB v4.14.9 (Redis-compatible) |
| Embeddings | Ollama `nomic-embed-text` — **runs on host, not in Docker** |
| Reranker | sentence-transformers CrossEncoder (in-process) |
| Containers | Docker Compose |

---

## Prerequisites

- **Docker** and **Docker Compose** v2
- **Ollama** running on your host machine with `nomic-embed-text` pulled
- macOS or Linux (Windows via WSL2)

```bash
# Install Ollama: https://ollama.com
ollama pull nomic-embed-text
```

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/tinosingh/peanut.git
cd peanut

# 2. Start the stack
./peanut.sh start

# 3. Check everything is healthy
./peanut.sh health

# 4. Drop files into the watch folder
cp ~/Documents/emails.mbox ./drop-zone/
cp ~/Documents/report.pdf  ./drop-zone/

# 5. Open the TUI to watch ingestion progress
./peanut.sh tui
```

---

## peanut.sh

```
./peanut.sh start       Start the Docker Compose stack
./peanut.sh stop        Stop the stack
./peanut.sh restart     Restart the stack
./peanut.sh reset       Wipe all data and restart (destructive)
./peanut.sh status      Show container status
./peanut.sh health      Check all service health endpoints
./peanut.sh logs        Tail all logs
./peanut.sh logs <svc>  Tail logs for a specific service (e.g. pkg-ingest)
./peanut.sh tui         Launch the interactive Textual TUI
./peanut.sh help        Show help
```

---

## TUI Navigation

Launch with `./peanut.sh tui`. The TUI has six tabs:

| Tab | Key | Purpose |
|---|---|---|
| Dashboard | `1` | System health, embedding metrics, outbox depth |
| Intake | `2` | Live per-file ingest progress (refreshes every 3s) |
| Search | `3` | Hybrid BM25 + vector + rerank search |
| Entities | `4` | Entity resolution merge queue |
| Settings | `5` | Search weights, PII report, bulk redact |
| Graph | `6` | FalkorDB knowledge graph browser |

Global keys: `ctrl+h` help · `q` quit

---

## Drop Zone

The drop zone is a regular folder at `./drop-zone/` on your host. The ingest worker
watches it continuously. Supported formats:

| Format | Extension |
|---|---|
| Email mailbox | `.mbox`, `.mbx` |
| PDF document | `.pdf` |
| Markdown / plain text | `.md`, `.markdown`, `.txt` |

**macOS tip:** Drag the `drop-zone/` folder to your Finder sidebar for one-click access.

```bash
# Pause ingestion temporarily
touch ./drop-zone/.pause

# Resume
rm ./drop-zone/.pause
```

---

## Services & Ports

| Service | Container | Port | Purpose |
|---|---|---|---|
| PostgreSQL + pgvector | `pkg-db` | `5432` | Primary datastore |
| FalkorDB | `pkg-graph` | `6379` | Knowledge graph |
| TUI Controller | `pkg-tui` | `8000` | FastAPI REST + Textual |
| Ingest Worker | `pkg-ingest` | — | File watcher + embedding worker |

---

## REST API

The TUI controller exposes a REST API at `http://localhost:8000`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Service health (no auth) |
| `GET` | `/metrics` | Prometheus metrics (no auth) |
| `POST` | `/search` | Hybrid search `{q, limit}` |
| `GET` | `/entities/merge-candidates` | Entity merge queue |
| `POST` | `/entities/merge` | Execute entity merge |
| `DELETE` | `/entities/{type}/{id}` | Soft delete |
| `GET` | `/config` | Read runtime config |
| `POST` | `/config` | Update search weights |
| `GET` | `/pii/report` | PII audit report |
| `POST` | `/pii/bulk-redact` | Redact all PII chunks |
| `POST` | `/ingest/text` | Queue raw text (MCP) |
| `GET` | `/graph/nodes` | Query FalkorDB nodes (MCP) |

Set `X-API-Key` header for authenticated endpoints. Configure keys via:
```bash
API_KEY_READ=<key>   # read-only access
API_KEY_WRITE=<key>  # write access
```

---

## Makefile

```bash
make up                    # docker compose up -d
make down                  # docker compose down
make reset                 # wipe volumes and restart
make logs                  # follow all logs
make tui                   # open TUI
make migrate-up            # run Alembic migrations
make backup                # pg_dump to ./data/backups/
make restore-from-backup   # restore latest backup
make test-backup-restore   # full backup/restore cycle
make sanity                # check for orphaned chunks
make audit                 # Trivy image security scan
make hard-delete           # physical delete (30-day quarantine gate)
make scan-pii              # run PII scanner on unscanned chunks
make reindex               # re-embed all chunks
```

---

## Development

```bash
# Live code reload without container rebuilds
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Run tests
pytest tests/ --tb=short -q

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

---

## Architecture

```
drop-zone/          ← watched by ingest-worker
    └── file.pdf

pkg-ingest          ← watchfiles + chunker + PII scanner
    └── embedding_worker  ← Ollama embeddings (nomic-embed-text on host)
    └── outbox_worker     ← PostgreSQL outbox → FalkorDB graph writes

pkg-db (PostgreSQL)
    ├── documents   ← source files + metadata
    ├── chunks      ← text chunks + pgvector embeddings
    ├── persons     ← extracted persons (entity resolution)
    ├── outbox      ← async FalkorDB write queue
    └── config      ← runtime tunable parameters

pkg-graph (FalkorDB)
    └── graph: pkg  ← Person/Document/Concept nodes + edges

pkg-tui (FastAPI + Textual)
    ├── REST API    ← search, entities, config, PII, ingest, graph
    └── TUI         ← Textual terminal interface
```

Key design rules:
- **All FalkorDB writes via outbox pattern** — never write directly from ingest path
- **Single atomic transaction** per ingest: document + persons + outbox INSERT
- **FOR UPDATE SKIP LOCKED** in embedding worker — safe concurrent pickup
- **No auto-merge** — entity resolution always requires human confirmation
- **Ollama on host only** — never add Ollama as a Docker service

---

## Environment Variables

```bash
POSTGRES_URL        postgresql://pkg:pkg@pkg-db:5432/pkg
FALKORDB_HOST       pkg-graph
FALKORDB_PORT       6379
OLLAMA_URL          http://host.docker.internal:11434
DROP_ZONE_PATH      ./drop-zone
VAULT_SYNC_PATH     ./vault-sync
API_PORT            8000
API_KEY_READ        (optional)
API_KEY_WRITE       (optional)
EMBED_MODEL         nomic-embed-text
LOG_LEVEL           INFO
```

---

## License

MIT
