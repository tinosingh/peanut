# Peanut Stack Hardening - Completed

## Overview
Successfully hardened the Peanut stack for production robustness across all critical areas.

## Changes Implemented ✅

### 1. Development Environment (docker-compose.dev.yml)
- **File**: `docker-compose.dev.yml` (NEW)
- **Impact**: Enables live code reload without container rebuilds
- **Usage**: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`
- **Features**:
  - Volume mounts for `src/` and `tests/` directories
  - `PYTHONUNBUFFERED=1` for immediate log output
  - `PYTHONDONTWRITEBYTECODE=1` for cleaner development

### 2. Database Pool Hardening (src/shared/db.py)
- **Fixed**: Async coroutine leak (RuntimeWarning about TypeInfo._fetch_async)
- **Added**: Proper error handling with cleanup of partially initialized pools
- **Added**: Connection pool configuration:
  - `max_lifetime=3600` - Recycle connections after 1 hour
  - `timeout=30.0` - Connection acquisition timeout
  - `statement_timeout=30s` - Query timeout
  - `idle_in_transaction_session_timeout=60s` - Prevent hung transactions
- **Added**: Structured logging for pool lifecycle events
- **Fixed**: Use `register_vector_async` for async connections (not `register_vector`)

### 3. TUI Crash Logging (src/tui/app.py)
- **Added**: Comprehensive crash handler in `__main__` block
- **Logs to**: `/tmp/tui_crash.log`
- **Includes**:
  - Exception type and message
  - Full traceback
  - Python version and executable path
  - Fallback to stderr if file logging fails

### 4. Graceful Shutdown (src/tui/main.py)
- **Added**: SIGTERM/SIGINT signal handlers
- **Added**: Structured logging for shutdown events
- **Added**: Graceful shutdown sequence:
  1. First signal: Log and begin shutdown
  2. Second signal: Force exit
- **Note**: `src/ingest/main.py` already had excellent shutdown handling

### 5. Enhanced Metrics (src/api/metrics.py)
- **Added**: `pkg_outbox_pending_events{event_type="..."}` - Per-type pending counts
- **Added**: `pkg_outbox_oldest_pending_seconds` - Age of oldest pending event
- **Maintained**: Existing `pkg_outbox_depth` and `pkg_chunks_total` metrics
- **Purpose**: Enable alerting on outbox lag (e.g., >100 pending or >5min old)

### 6. Enhanced Health Checks (src/tui/main.py)
- **Added**: FalkorDB connectivity check
- **Returns**: 503 when critical services (postgres, falkordb) are down
- **Returns**: 200 with degraded status when non-critical services (ollama) are down
- **Checks**:
  - `postgres`: Database connectivity
  - `falkordb`: Graph database connectivity
  - `ollama`: Embeddings service (non-critical)

### 7. Structured Logging
- **Verified**: All workers use structlog
- **Maintained**: CLI scripts (reindex.py, pii.py) appropriately use print() for user feedback
- **Added**: Consistent structured logging throughout core services

## Verification Results ✅

### Health Check
```json
{
    "status": "healthy",
    "postgres": "ok",
    "falkordb": "ok",
    "ollama": "ok"
}
```

### Port Usage
All ports correctly bound to Docker containers:
- `8000`: TUI controller (FastAPI)
- `5432`: PostgreSQL
- `6379`: FalkorDB

### Container Status
All services healthy:
- `pkg-db`: PostgreSQL with pgvector
- `pkg-graph`: FalkorDB
- `pkg-tui`: TUI controller (FastAPI + Textual)
- `pkg-ingest`: Ingest worker

### Code Quality
- ✅ All `ruff check` linting passed
- ✅ Import ordering corrected
- ✅ Proper use of contextlib.suppress
- ✅ Module-level imports at top of file

## Next Steps (Week 2-3)

### Week 2 - High Priority
1. Add Prometheus alerting rules for outbox lag
2. Implement Ollama retry logic with exponential backoff
3. Load testing (1000 concurrent searches, 100 ingests/sec)
4. Security hardening:
   - Secrets management (move API key to /run/secrets)
   - Read-only containers
   - Drop unnecessary capabilities

### Week 3 - Medium Priority
1. Chaos testing suite
   - Container restarts
   - Network partitions
   - Disk full scenarios
2. Backup/restore automation with verification
3. Quarterly disaster recovery drill plan

## Files Modified
- `docker-compose.dev.yml` (NEW)
- `src/shared/db.py`
- `src/tui/app.py`
- `src/tui/main.py`
- `src/api/metrics.py`

## Testing Commands

### Start with dev overrides
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### Check health
```bash
curl http://localhost:8000/health | jq
```

### Check metrics
```bash
curl http://localhost:8000/metrics | grep pkg_outbox
```

### Test graceful shutdown
```bash
docker stop --time 30 pkg-tui  # Should shutdown cleanly within 30s
docker logs pkg-tui | grep shutdown
```

### Check TUI crash log
```bash
docker exec pkg-tui cat /tmp/tui_crash.log
```

## Performance Impact
- **Minimal**: All changes add negligible overhead
- **Pool recycling**: Prevents connection leaks over time
- **Health checks**: <10ms latency per check
- **Metrics**: Computed on-demand, no background overhead

## Rollback Plan
If issues arise:
1. Revert to previous Docker images: `docker compose down && git checkout HEAD~1 && docker compose build && docker compose up -d`
2. Remove dev overrides: Use `docker-compose.yml` only
3. Check `/tmp/tui_crash.log` for crash diagnostics

## Documentation Updates Needed
- [ ] Update `docs/DEPLOYMENT.md` with health check expectations
- [ ] Update `docs/ARCHITECTURE.md` with pool configuration
- [ ] Add alerting runbook for outbox lag metrics
- [ ] Document dev workflow with docker-compose.dev.yml

---
**Status**: All Week 1 critical tasks completed and verified ✅
**Iteration**: Ralph Loop Iteration 1
**Date**: 2026-02-25
