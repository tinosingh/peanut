# End-to-End Integration Test Guide

This guide walks through a complete manual integration test of the Peanut system.

## Prerequisites

```bash
# Install/start Ollama on host
brew install ollama (macOS)
ollama serve &
ollama pull nomic-embed-text

# Install dependencies
pip install -e ".[ingest,tui,test]"

# Ensure Docker Compose available
docker --version
docker-compose --version
```

## Test Procedure

### Phase 1: Stack Startup (5 min)

```bash
# Start services
docker-compose up -d

# Wait for services to be ready
sleep 15

# Verify services are running
docker-compose ps
# Expected: pkg-db, pkg-graph, pkg-ingest, pkg-tui all UP

# Health check
curl http://localhost:8000/health
# Expected: {"status": "ok"}

# Verify Ollama connection from container
docker exec pkg-ingest curl http://host.docker.internal:11434/api/tags
# Expected: {"models": [{"name": "nomic-embed-text:latest", ...}]}

# Run migrations
docker-compose exec pkg-db alembic upgrade head
# Expected: "No migrations to run"
```

### Phase 2: Document Ingestion (10 min)

Create sample test documents:

```bash
# Create sample email (MBOX format)
cat > drop-zone/sample.mbox << 'MBOX'
From: alice@example.com
To: bob@example.com
Subject: Q4 Budget Review and Project Timeline
Date: Mon, 25 Dec 2024 10:00:00 +0000

The Q4 budget allocation needs review. Project timeline is as follows:
- Phase 1: Jan 2025
- Phase 2: Feb 2025
- Phase 3: Mar 2025

Please review the attached proposals and provide feedback.

--
Alice Smith
CEO
MBOX

# Create sample markdown
cat > drop-zone/notes.md << 'MD'
# Project Notes

## Overview
The PKG system integrates Postgres, FalkorDB, and Ollama for semantic search.

## Architecture
- Embedding pipeline via Ollama (nomic-embed-text)
- Graph database for entity relationships
- BM25 + ANN hybrid search

## Team
- Alice Smith (PM)
- Bob Johnson (Engineering)
MD

# Check watcher detected files
sleep 5
docker-compose logs pkg-ingest | grep "file_detected"
# Expected: 2 entries (sample.mbox, notes.md)
```

### Phase 3: Embedding Verification (5 min)

```bash
# Check embedding progress
docker exec pkg-db psql -U peanut -d pkg << 'SQL'
SELECT 
  embedding_status,
  COUNT(*) as count
FROM chunks
GROUP BY embedding_status
ORDER BY embedding_status;
SQL
# Expected output:
#  embedding_status | count
# ------------------+-------
#  done             |    15
#  (1 row)

# Check embedding vector dimensions
docker exec pkg-db psql -U peanut -d pkg << 'SQL'
SELECT 
  id, 
  LENGTH(embedding::text) as vector_size,
  embedding_status
FROM chunks
LIMIT 1;
SQL
# Expected: vector_size > 100 (768-dimensional for nomic-embed-text)

# Check PII detection
docker exec pkg-db psql -U peanut -d pkg << 'SQL'
SELECT 
  pii_detected,
  COUNT(*) as count
FROM chunks
GROUP BY pii_detected;
SQL
# Expected: Some chunks flagged as PII (email addresses)
```

### Phase 4: Graph Population (3 min)

```bash
# Check FalkorDB has persons
docker exec pkg-graph redis-cli << 'CYPHER'
GRAPH.QUERY pkg "MATCH (p:Person) RETURN COUNT(p)"
CYPHER
# Expected: 2 (alice@example.com, bob@example.com)

# Check documents
docker exec pkg-graph redis-cli << 'CYPHER'
GRAPH.QUERY pkg "MATCH (d:Document) RETURN COUNT(d)"
CYPHER
# Expected: 2 (sample.mbox, notes.md)

# Check edges
docker exec pkg-graph redis-cli << 'CYPHER'
GRAPH.QUERY pkg "MATCH (p:Person)-[r]-(d:Document) RETURN COUNT(r)"
CYPHER
# Expected: 4 or more (SENT, RECEIVED edges)
```

### Phase 5: Search API Tests (10 min)

```bash
# Test 1: BM25 search
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"q": "budget", "limit": 5}' | jq .

# Expected:
# - results array with 1-2 hits
# - snippet contains "budget"
# - degraded: false
# - scores: bm25_score > 0, vector_score > 0

# Test 2: Semantic search (vector similarity)
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"q": "architecture timeline", "limit": 5}' | jq .

# Expected:
# - 2-3 results mentioning project phases
# - vector_score should be reasonable

# Test 3: Cross-cutting search
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"q": "alice bob", "limit": 5}' | jq .

# Expected:
# - Results mentioning both names
# - Should find emails with both sender/recipient

# Test 4: No results case
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"q": "xyzabc", "limit": 5}' | jq .

# Expected:
# - results: []
# - degraded: false
```

### Phase 6: Entity Resolution (5 min)

```bash
# Get merge candidates
curl http://localhost:8000/entities/merge-candidates | jq .

# Expected: candidates array (may be empty if only 2 unique persons)

# Create duplicate person for testing
docker exec pkg-db psql -U peanut -d pkg << 'SQL'
INSERT INTO persons (id, email, display_name, pii)
VALUES 
  ('99999999-9999-9999-9999-999999999999', 'alice.s@example.com', 'Alice S', true);
SQL

# Get candidates again (should suggest merging)
curl http://localhost:8000/entities/merge-candidates | jq '.candidates[0]'

# Test merge
curl -X POST "http://localhost:8000/entities/merge?name_a=Alice+Smith&name_b=Alice+S" | jq .

# Expected:
# - merged_from and merged_into IDs
# - No error

# Verify merge in graph
docker exec pkg-graph redis-cli << 'CYPHER'
GRAPH.QUERY pkg "MATCH (p:Person {email: 'alice@example.com'})<-[r]-(d:Document) RETURN COUNT(r)"
CYPHER
# Expected: Same edge count as before (merged_from marked invalid, not deleted)
```

### Phase 7: Vault Sync (5 min)

```bash
# Check if vault-sync directory exists
ls -la vault-sync/documents/ 2>/dev/null || echo "Directory not created yet"

# The vault-sync is created during ingest if VAULT_SYNC_PATH is set
# Check environment
docker-compose config | grep VAULT_SYNC_PATH
# Expected: VAULT_SYNC_PATH: ./vault-sync

# Wait for vault sync to write files
sleep 5

# Check for markdown files
ls vault-sync/documents/ | head -3
# Expected: Files like "Q4_Budget_Review_sample_XXXXXXXX.md"

# Verify document front matter
head -10 vault-sync/documents/*.md | head -20
# Expected: YAML front matter with doc_id, source_type, etc.
```

### Phase 8: Metrics & Health (3 min)

```bash
# Get Prometheus metrics
curl http://localhost:8000/metrics

# Expected output (Prometheus format):
# chunks_embedded_total 15
# search_requests_total 4
# ...

# Check log output (structured logging)
docker-compose logs --tail=50 pkg-ingest | grep -E "embeddings_written|outbox_event_processed"

# Expected: Structured JSON logs with latency_ms, counts, etc.
```

### Phase 9: Hard Delete & Backup (5 min)

```bash
# Soft delete a document
curl -X POST "http://localhost:8000/entities/soft-delete?entity_type=document&entity_id=<UUID>"

# Verify it's marked deleted_at
docker exec pkg-db psql -U peanut -d pkg << 'SQL'
SELECT id, deleted_at FROM documents WHERE deleted_at IS NOT NULL;
SQL

# Backup database
make backup

# Verify backup file exists
ls -lh data/backups/ | head -1

# Test restore (dry-run)
docker exec pkg-db pg_dump -U peanut -d pkg | gzip > /tmp/test-backup.sql.gz
# File should exist
ls -lh /tmp/test-backup.sql.gz
```

### Phase 10: TUI Visual Test (5 min)

```bash
# Start TUI
make tui

# Test TUI screens:

# 1. Dashboard (default)
#    - Shows: chunks pending, search cache hits, outbox queue
#    - Check for any red warnings

# 2. Search Screen (press 's')
#    - Type: "budget"
#    - Should see 1-2 results with snippets
#    - Verify rerank_score is present

# 3. Entities Screen (press 'e')
#    - Should show persons, documents, chunks counts
#    - Try merge: press 'M', confirm

# 4. Graph Screen (press 'g')
#    - Should show tree of documents/persons/relationships
#    - Press 'Enter' to drill into a node
#    - Press 'X' to export as Vis.js HTML (opens in browser)
#    - Visual should show nodes + edges

# 5. Settings (press 't')
#    - Update search config, verify it persists
#    - Change rrf_k or cache_ttl

# Exit: Ctrl+D or press 'q'
```

## Cleanup

```bash
# Shutdown stack
docker-compose down

# (Optional) Remove volumes to reset
docker-compose down -v

# Stop Ollama
# pkill ollama

# Remove test data
rm -rf drop-zone/* vault-sync/*
```

## Success Criteria

✅ All 10 phases complete without errors
✅ Search returns relevant results (BM25 + ANN both working)
✅ Entities can be merged
✅ Graph is populated correctly
✅ TUI displays data and allows navigation
✅ Metrics endpoint returns data
✅ Backup/restore works
✅ Logging is structured and readable
✅ No "CANARY VIOLATION" alerts in dashboard
✅ No outbox dead-letters

## Troubleshooting

See `docs/DEPLOYMENT.md` for common issues and fixes.

## Performance Baseline

For reference, expected latencies:
- Embed email (500 chunks): 2-5s
- Search query: 100-500ms
- Entity merge: 10-50ms
- Graph export: <100ms

If slower, check:
- `docker stats` for CPU/memory pressure
- `docker logs` for errors in workers
- `curl http://localhost:11434/api/tags` to ensure Ollama responsive
