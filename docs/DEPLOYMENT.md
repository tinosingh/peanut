# Deployment & Troubleshooting Guide

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Ollama running locally on port 11434
- Python 3.12 + pip

### Setup

```bash
# Clone and enter directory
git clone <repo> peanut
cd peanut

# Install dependencies
pip install -e ".[ingest,tui,test]"

# Start services
docker-compose up -d

# Run migrations
make migrate-up

# Start TUI
make tui
```

### Ollama Setup

```bash
# Install Ollama (macOS)
brew install ollama

# Start Ollama daemon
ollama serve

# In another terminal, pull embedding model
ollama pull nomic-embed-text

# Verify it's listening
curl http://localhost:11434/api/tags
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `POSTGRES_URL` | postgresql://pkg:changeme@pkg-db:5432/pkg | Database connection |
| `FALKORDB_HOST` | pkg-graph | Graph database host |
| `FALKORDB_PORT` | 6379 | Graph database port (Redis) |
| `OLLAMA_URL` | http://host.docker.internal:11434 | Embedding service |
| `EMBED_MODEL` | nomic-embed-text | Ollama model name |
| `API_PORT` | 8000 | FastAPI port |
| `LOG_LEVEL` | info | Python logging level |
| `DROP_ZONE_PATH` | ./drop-zone | File ingest directory |
| `VAULT_SYNC_PATH` | ./vault-sync | Obsidian sync directory |

### Setting Env Vars

**Docker Compose:**
```yaml
environment:
  OLLAMA_URL: "http://host.docker.internal:11434"
  LOG_LEVEL: "debug"
```

**Local development:**
```bash
export OLLAMA_URL="http://localhost:11434"
export LOG_LEVEL="debug"
python -m src.tui.app
```

---

## Docker Compose Services

```yaml
pkg-db:        Postgres 17 + pgvector 0.8
pkg-graph:     FalkorDB v4.14.9 (Redis)
pkg-ingest:    Ingest worker (watcher, embedding, outbox)
pkg-tui:       FastAPI + Textual TUI
```

### Health Checks

```bash
# Database
docker exec pkg-db psql -U pkg -d pkg -c "SELECT 1"

# Graph
docker exec pkg-graph redis-cli PING

# Ollama (on host)
curl http://localhost:11434/api/tags

# API
curl http://localhost:8000/health
```

---

## Common Issues & Fixes

### Issue: "Ollama connection refused"

**Symptom:** Embedding worker logs show `ConnectionError`

**Causes:**
1. Ollama not running on host
2. Wrong `OLLAMA_URL` env var
3. Docker can't reach host (Mac/Windows)

**Fix:**
```bash
# Start Ollama
ollama serve &

# Verify listening on correct address
netstat -an | grep 11434

# Update env var in docker-compose.yml
# Mac/Windows: http://host.docker.internal:11434
# Linux: http://172.17.0.1:11434

# Restart containers
docker-compose restart pkg-ingest pkg-tui
```

### Issue: "No route to host" when accessing database

**Symptom:** API returns 503, logs show connection timeout

**Fix:**
```bash
# Verify services running
docker-compose ps

# Check network
docker network ls
docker network inspect peanut_default

# Restart and check logs
docker-compose down
docker-compose up -d
docker-compose logs -f pkg-db
```

### Issue: PII detection slow or disabled

**Symptom:** spaCy model not loaded

**Fix:**
```bash
# Install spaCy model inside container
docker exec pkg-ingest python -m spacy download en_core_web_sm

# Or disable NLP (regex-only)
# Edit src/ingest/pii.py: _get_nlp() returns None
```

### Issue: Search returns no results

**Symptoms:** All searches degrade, BM25 returns 0

**Causes:**
1. No documents ingested yet
2. Text index not built
3. PII redaction too aggressive

**Fix:**
```bash
# Ingest sample documents
cp tests/fixtures/*.mbox drop-zone/

# Wait for embedding worker to process
sleep 10

# Check if chunks exist
docker exec pkg-db psql -U pkg -d pkg -c "SELECT COUNT(*) FROM chunks"

# Rebuild index if needed
docker exec pkg-db psql -U pkg -d pkg -c "REINDEX INDEX idx_chunks_tsvector"
```

### Issue: Graph export (Vis.js) blank or errors

**Symptom:** Click 'X' → browser opens empty graph

**Causes:**
1. No document-person edges in FalkorDB
2. Graph query returns 0 rows

**Fix:**
```bash
# Check FalkorDB has data
docker exec pkg-graph redis-cli
> GRAPH.QUERY pkg "MATCH (n) RETURN COUNT(n)"

# If 0, trigger outbox sync
docker-compose restart pkg-ingest
sleep 5

# Retry export
```

### Issue: "Outbox event failed" loops

**Symptom:** Same row_id repeatedly logs error

**Causes:**
1. FalkorDB down
2. Malformed outbox event
3. Poison pill (unrecoverable event)

**Fix:**
```bash
# Check FalkorDB
docker exec pkg-graph redis-cli PING

# Inspect failed event
docker exec pkg-db psql -U pkg -d pkg -c "
  SELECT id, event_type, payload, error FROM outbox WHERE failed = true
"

# If poison pill, manually mark processed
docker exec pkg-db psql -U pkg -d pkg -c "
  UPDATE outbox SET processed_at = now() WHERE id = <row_id>
"
```

### Issue: Embedding job stuck / max retry exceeded

**Symptom:** `embedding_status = 'failed'` for chunks

**Causes:**
1. Ollama model too large, OOM
2. Network timeouts
3. Malformed text (weird encoding)

**Fix:**
```bash
# Check Ollama resources
ollama show nomic-embed-text | grep parameters

# Reset embedding status to retry
docker exec pkg-db psql -U pkg -d pkg -c "
  UPDATE chunks SET embedding_status = 'pending', retry_count = 0
  WHERE embedding_status = 'failed'
"

# Watch retry
docker-compose logs -f pkg-ingest | grep embedding
```

---

## Monitoring & Logging

### Structured Logs

All logs are structured (JSON) for easy aggregation:

```bash
# View search logs
docker-compose logs pkg-tui | grep search_completed

# View embedding performance
docker-compose logs pkg-ingest | grep embeddings_written

# View graph sync
docker-compose logs pkg-ingest | grep outbox_event_processed
```

### Prometheus Metrics

```bash
# Get metrics
curl http://localhost:8000/metrics

# Example:
# chunks_embedded_total 1242
# search_latency_ms_bucket{le="100"} 45
```

### Database Stats

```bash
# Chunk count by status
docker exec pkg-db psql -U pkg -d pkg -c "
  SELECT embedding_status, COUNT(*) FROM chunks GROUP BY embedding_status
"

# Document ingestion timeline
docker exec pkg-db psql -U pkg -d pkg -c "
  SELECT DATE(ingested_at), COUNT(*) FROM documents 
  GROUP BY DATE(ingested_at) ORDER BY DATE DESC LIMIT 30
"

# PII detection rate
docker exec pkg-db psql -U pkg -d pkg -c "
  SELECT pii_detected, COUNT(*) FROM chunks GROUP BY pii_detected
"
```

---

## Backup & Restore

### Backup

```bash
# One-time backup
make backup

# Output: ./data/backups/backup-YYYYMMDD-HHMMSS.sql.gz

# List backups
ls -lh data/backups/
```

### Restore

```bash
# Restore latest
make restore-from-backup

# Or specify file
docker exec pkg-db pg_restore --clean --if-exists -U pkg -d pkg /backups/backup-<date>.sql.gz
```

### Verify Backup

```bash
make test-backup-restore
```

---

## Scaling

### Tuning

**Postgres connection pool:**
```
POSTGRES_POOL_MIN_SIZE=5
POSTGRES_POOL_MAX_SIZE=20
```

**Embedding batch size:**
```python
EMBED_BATCH_SIZE = 200  # src/ingest/embedding_worker.py
```

**Search cache TTL:**
```sql
UPDATE config SET value = '120' WHERE key = 'search_cache_ttl'  -- 2 mins
```

### Multi-instance

Currently single-instance only. To scale:
1. Multiple embedding workers (each takes different chunks via FOR UPDATE SKIP LOCKED)
2. Multiple outbox workers (each takes different rows)
3. Read replicas for search API (read-only Postgres)

---

## Maintenance

### Daily

- Monitor logs for errors
- Check /metrics for latency spikes
- Verify daily backups

### Weekly

- Run `make hard-delete --confirm` to purge 30+ day old data
- Review canary guard alerts (CANARY VIOLATION)
- Check disk space (embeddings are ~4KB per chunk)

### Monthly

- Update embeddings model if available
- Review entity resolution threshold (tune via `/config/merge_threshold`)
- Analyze search latency trends

---

## Debugging

### Enable Debug Logging

```bash
export LOG_LEVEL=debug
docker-compose restart pkg-ingest pkg-tui
```

### Connect to Databases

```bash
# Postgres
docker exec -it pkg-db psql -U pkg -d pkg

# FalkorDB
docker exec -it pkg-graph redis-cli
> GRAPH.QUERY pkg "MATCH (n:Person) RETURN n.email LIMIT 5"
```

### Inspect Running Container

```bash
# Shell into ingest worker
docker exec -it pkg-ingest bash

# Check what files are being watched
ls -lh drop-zone/
ps aux | grep python
```

### Test End-to-End

```bash
# 1. Drop a sample file
cp tests/fixtures/sample.mbox drop-zone/

# 2. Wait for ingest
sleep 10

# 3. Search for it
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"q": "test", "limit": 5}'

# 4. Check graph
curl http://localhost:8000/metrics | grep graph
```
