# Phase 1 Testing Plan: Token Overflow Fix

## Pre-Deployment Checklist

- [ ] Git status clean (commit changes or stash)
- [ ] Database backup available
- [ ] Ollama running and accessible
- [ ] Drop-zone empty or backed up

## Deployment Steps

### Step 1: Migrate Database Schema

```bash
# Apply the new token_count column migration
make migrate-up
```

**Expected output:**
```
Upgrade complete. Run 'make migrate-up' if schema changes are included.
```

**Verify migration:**
```bash
docker compose exec pkg-db psql -U pkg -d pkg -c "
  SELECT column_name, data_type FROM information_schema.columns
  WHERE table_name='chunks' AND column_name='token_count';"
```

Expected: Should return `token_count | integer`

### Step 2: Restart Services (Forces Rebuild)

```bash
# Stop all services
make down

# Rebuild Docker images (includes new tiktoken dependency)
make up
```

**Monitor startup:**
```bash
docker compose logs -f ingest-worker
```

Expected output patterns:
- `Successfully installed tiktoken` (in build logs)
- `embedding_worker_started` (in ingest-worker logs)
- Zero errors during initialization

**Verify Ollama connectivity:**
```bash
docker compose logs ingest-worker | grep -i ollama
```

Expected: Should mention successful connection or polling

### Step 3: Prepare Test PDF

Use a PDF that previously caused token overflow errors. If you don't have one:

```bash
# Create a test PDF with many chunks (~50-100 chunks to force batching)
python3 << 'EOF'
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import os

# Create a large PDF (100 pages, ~50K+ words)
pdf_path = "drop-zone/test_large.pdf"
os.makedirs("drop-zone", exist_ok=True)
c = canvas.Canvas(pdf_path, pagesize=letter)

text = "This is a test document. " * 20  # Repeating text per paragraph
for page_num in range(100):
    c.drawString(50, 750, f"Page {page_num + 1}")
    y = 700
    for para in range(20):
        c.drawString(50, y, text)
        y -= 20
    c.showPage()

c.save()
print(f"Created {pdf_path}")
EOF
```

### Step 4: Monitor Ingestion

```bash
# Watch ingest-worker logs in real-time
docker compose logs -f ingest-worker
```

**Look for these log patterns:**

#### Success Indicators ✓
```
embeddings_batch_completed count=<N> num_batches=<M> elapsed_ms=<T>
embeddings_written count=<N> batch_size=<N>
document_ingested doc_id=... source_path=...
```

#### Token Accuracy Validation
```
# Chunks should be under 600 tokens (our max_tokens setting)
# Example: "chunk_text" field has ~600 tokens
```

#### Batch Sizing Log (Should show 4-8 chunks per batch)
```
embeddings_batch_completed total_count=100 num_batches=15 elapsed_ms=45000
# 100 chunks / 15 batches = 6.7 chunks per batch ✓
```

### Step 5: Verify No Context Overflow Errors

```bash
# Check for "context length" or "context overflow" errors
docker compose logs ingest-worker | grep -i context

# Should return NOTHING (empty result)
```

If errors appear:
```bash
# Get the full error context
docker compose logs ingest-worker | grep -A 5 -B 5 "context"
```

### Step 6: Validate Chunk Status in Database

```bash
# Check final embedding status (should all be 'done')
docker compose exec pkg-db psql -U pkg -d pkg -c "
  SELECT embedding_status, COUNT(*)
  FROM chunks
  WHERE doc_id = (SELECT id FROM documents ORDER BY ingested_at DESC LIMIT 1)
  GROUP BY embedding_status;"
```

Expected output:
```
embedding_status | count
-----------------+-------
done             |  50
```

(No 'failed' or 'processing' statuses for new chunks)

### Step 7: Validate Token Count Storage

```bash
# Check that token_count was stored for new chunks
docker compose exec pkg-db psql -U pkg -d pkg -c "
  SELECT
    COUNT(*) as total_chunks,
    COUNT(token_count) as with_token_count,
    COUNT(token_count) * 100.0 / COUNT(*) as pct_populated,
    MIN(token_count) as min_tokens,
    MAX(token_count) as max_tokens,
    ROUND(AVG(token_count)::numeric, 1) as avg_tokens
  FROM chunks
  WHERE doc_id = (SELECT id FROM documents ORDER BY ingested_at DESC LIMIT 1);"
```

Expected output:
```
total_chunks | with_token_count | pct_populated | min_tokens | max_tokens | avg_tokens
--------------+------------------+---------------+------------+------------+------------
50           | 50               | 100.0         | 180        | 590        | 420.5
```

## Performance Benchmarks

Test ingestion speed of 100-chunk document:

```bash
# Clear previous documents (optional)
docker compose exec pkg-db psql -U pkg -d pkg -c "
  DELETE FROM documents WHERE ingested_at > now() - interval '1 hour';"

# Time the ingestion
time docker compose exec pkg-ingest python -c "
import asyncio
from src.ingest.main import _handle_file
asyncio.run(_handle_file('drop-zone/test_large.pdf', 'test_hash'))
"
```

**Expected metrics** (Apple M2 16GB):
- 100 chunks: ~20-30 seconds (including PDF parsing + chunking + embedding)
- Embedding latency: ~200ms per chunk
- Zero retry/overflow errors

## Troubleshooting

### "tiktoken not found" error
**Symptom:** `ModuleNotFoundError: No module named 'tiktoken'`

**Fix:**
```bash
# Rebuild container (forces pip install of ingest dependencies)
make down
docker system prune -a --volumes  # Clean slate
make up
```

### "context length exceeded" errors still appear
**Symptom:** `HTTPStatusError: 400 ... context`

**Cause:** Batch sizing didn't trigger, or token limit too high

**Fix:**
1. Check logs: `docker compose logs ingest-worker | grep "batch_overflow"`
2. Verify token_count column exists: `make migrate-up` again
3. Reduce `EMBED_BATCH_TOKEN_LIMIT` to 1024 (more conservative)
4. Check Ollama logs: `ollama logs` (on host machine)

### Chunks marked as "failed"
**Symptom:** `embedding_status = 'failed'` in database

**Check:**
```bash
docker compose exec pkg-db psql -U pkg -d pkg -c "
  SELECT id, text, retry_count
  FROM chunks
  WHERE embedding_status = 'failed'
  LIMIT 5;"
```

**Common causes:**
- Single chunk genuinely exceeds 600 tokens (shouldn't happen, but check `token_count`)
- Ollama unresponsive
- Network timeout

### Migration failed or rolled back
**Symptom:** `psycopg.errors.UndefinedColumn: column "token_count" does not exist`

**Fix:**
```bash
# Check migration status
docker compose exec pkg-db psql -U pkg -d pkg -c "
  SELECT * FROM alembic_version;"

# If shows 0001, manually apply 0002:
make migrate-up
```

## Rollback Plan

If issues occur and you need to revert:

```bash
# Rollback migration
docker compose exec -e POSTGRES_URL="postgresql://pkg:...@pkg-db:5432/pkg" \
  pkg-ingest .venv/bin/alembic downgrade -1

# Use old code from git
git checkout HEAD~1 src/ingest/chunker.py src/ingest/embedding_worker.py

# Restart
make down && make up
```

## Success Criteria

Phase 1 is **PASSED** when:

1. ✅ Zero "context length exceeded" errors in 100+ chunk ingestion
2. ✅ All chunks show `embedding_status = 'done'` (no 'failed')
3. ✅ Batch logs show 4-8 chunks per batch
4. ✅ Token counts stored in database (`token_count` NOT NULL for new chunks)
5. ✅ Embedding latency <3000ms per chunk average
6. ✅ No errors in ingest-worker logs related to tokenization or batching

## Next Steps

Once Phase 1 passes:
- [ ] Commit changes: `git add -A && git commit -m "fix: implement accurate tokenization and dynamic batching"`
- [ ] Document results (optional: save logs to `PHASE1_TEST_RESULTS.md`)
- [ ] Proceed to Phase 2 (file type support for .docx, .pptx, images)
- [ ] Optional: Run harness tests if available
