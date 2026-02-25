# Peanut — Task List

<!-- Machine-parsable YAML task list. The agent reads this to pick work. -->
<!-- Status: pending | in_progress | done | blocked -->
<!-- Priority: P0 (critical) | P1 (high) | P2 (medium) | P3 (low) -->
<!-- Source: knowledge-base-prd-v3.2_1.md -->

```yaml
tasks:

  # ── Epic 0: Infrastructure Bootstrap ──────────────────────────────────────

  - id: T-000
    title: "Scaffold project source layout and Docker Compose stack"
    priority: P0
    status: done
    depends_on: []
    branch: "feat/T-000-scaffold-docker-compose"
    pr_url: ""
    head_sha: "32bc0eb9ac5cc0476bee5c27620adb7ea2d128b9"
    acceptance_criteria:
      - "src/ingest/, src/tui/, src/api/, db/migrations/ directories exist"
      - "docker-compose.yml defines: ingest-worker, pkg-db (pgvector), pkg-graph (falkordb), tui-controller"
      - "Ollama is NOT a service in compose — connects to host via host.docker.internal:11434"
      - "All 4 services pass health checks within 90s on cold start"
    prd_ref: "Epic 0"

  - id: T-001
    title: "Bootstrap pkg-db: init.sql + Alembic migrations"
    priority: P0
    status: done
    depends_on: ["T-000"]
    branch: "feat/T-001-db-init-alembic"
    pr_url: ""
    head_sha: "db0ece4f2761171cd3f505d4b57365264763b346"
    acceptance_criteria:
      - "init.sql creates all 6 tables: documents, persons, chunks, outbox, dead_letter, config"
      - "Alembic configured: alembic.ini + env.py targeting pkg-db"
      - "make migrate-up exits 0 with '0 pending migrations' on fresh init"
      - "config table seeded with default values from PRD §3.4"
    prd_ref: "Story 0.2"

  - id: T-002
    title: "Bootstrap pkg-graph: init FalkorDB empty 'pkg' graph"
    priority: P0
    status: done
    depends_on: ["T-000"]
    branch: "feat/T-002-falkordb-init"
    pr_url: ""
    head_sha: "12f29311ffad7c73f106a74efb549644e0eb1ea3"
    acceptance_criteria:
      - "Startup script creates empty 'pkg' graph on container init"
      - "redis-cli -p 6379 GRAPH.QUERY pkg 'MATCH (n) RETURN count(n)' returns 0"
    prd_ref: "Story 0.3"

  - id: T-003
    title: "Configure bind mounts: drop-zone and vault-sync"
    priority: P0
    status: done
    depends_on: ["T-000"]
    branch: "feat/T-003-T-004-mounts-makefile"
    pr_url: ""
    head_sha: "2fc77c7d8f2f0ed243bea718e59a8f5d8b04c948"
    acceptance_criteria:
      - "./drop-zone/ mounted read-only inside ingest-worker"
      - "./vault-sync/ mounted read-write; files written with chmod 444"
      - "docker exec ingest-worker ls /drop-zone/ shows test file"
    prd_ref: "Story 0.4"

  - id: T-004
    title: "Makefile targets: up, down, reset, logs, tui, backup, migrate-up, sanity, audit"
    priority: P0
    status: done
    depends_on: ["T-000"]
    branch: "feat/T-003-T-004-mounts-makefile"
    pr_url: ""
    head_sha: "2fc77c7d8f2f0ed243bea718e59a8f5d8b04c948"
    acceptance_criteria:
      - "All targets exit 0 on a fresh clone"
      - "make sanity returns 'OK: 0 orphaned chunks'"
      - "make test-backup-restore performs full backup/restore cycle and asserts row counts match"
      - "make hard-delete requires --confirm flag"
    prd_ref: "Story 0.5"

  - id: T-005
    title: "TUI skeleton: help overlay + footer bar + first-run welcome screen"
    priority: P0
    status: done
    depends_on: ["T-000"]
    branch: "feat/T-005-tui-skeleton"
    pr_url: ""
    head_sha: "4a8064c7631ffc4162efac3c970b0754d2003f3f"
    acceptance_criteria:
      - "? key toggles ModalScreen help overlay on any TUI screen"
      - "Textual footer bar shows plain-English description of focused action"
      - "WelcomeScreen shown when documents table is empty; dismissed after first ingest"
    prd_ref: "Stories 0.6, 0.7"

  # ── Epic 1: Data Intake & Lexical Search ──────────────────────────────────

  - id: T-010
    title: "Spike: embedding latency + chunk overlap A/B on target hardware"
    priority: P0
    status: done
    depends_on: ["T-001"]
    branch: "feat/T-010-embed-spike"
    pr_url: ""
    head_sha: "29bbcfadb8742e91290b03dbcb896ab3e0868eb7"
    acceptance_criteria:
      - "p95 embed latency measured for 1k and 10k chunks via Ollama nomic-embed-text on host"
      - "Recall@5 plotted for chunk overlap 25/50/100 tokens"
      - "nomic-embed-text vs all-minilm latency delta documented"
      - "Results committed to docs/spike-1.0-results.md; optimal overlap set in config table"
    prd_ref: "Story 1.0"

  - id: T-011
    title: "ingest-worker: watchfiles file watcher with ExtFilter"
    priority: P0
    status: done
    depends_on: ["T-000", "T-001"]
    branch: "feat/T-011-T-012-watcher-mbox"
    pr_url: ""
    head_sha: "7529d42578a8608b581a8db26d35212cd8d07ed1"
    acceptance_criteria:
      - "watchfiles 1.1.1 awatch() with ExtFilter for .mbox, .pdf, .md files"
      - "SHA-256 hash computed; file skipped if sha256 already in documents table"
      - "INGEST_SEMAPHORE limits to 10 concurrent parse+insert tasks"
    prd_ref: "Story 1.1"

  - id: T-012
    title: "MBOX parser: extract emails into documents + persons + outbox (single transaction)"
    priority: P0
    status: done
    depends_on: ["T-011"]
    branch: "feat/T-011-T-012-watcher-mbox"
    pr_url: ""
    head_sha: "7529d42578a8608b581a8db26d35212cd8d07ed1"
    acceptance_criteria:
      - "Extracts sender_email, sender_name, recipients, subject, body_text, date"
      - "Document row + persons UPSERT + outbox INSERT all in one DB transaction"
      - "Malformed messages written to dead_letter table"
      - "Outbox payload includes sender + recipients[] with field (to/cc/bcc)"
    prd_ref: "Story 1.2"

  - id: T-013
    title: "PDF + Markdown parsers; magika fallback for ambiguous extensions"
    priority: P0
    status: done
    depends_on: ["T-011"]
    branch: "feat/T-013-T-014-parsers-chunker-pii"
    pr_url: ""
    head_sha: "4ff9d0f205c203953b1a82631c35b30959cd8bd1"
    acceptance_criteria:
      - "pdfminer.six parses PDF; markdown parser handles .md/.markdown"
      - "magika 1.0.1 called only when extension absent/ambiguous (result.dl.ct_label)"
      - "Unknown content types written to dead_letter"
    prd_ref: "Story 1.3"

  - id: T-014
    title: "Chunker + PII scanner: 512-token chunks with overlap and pii_detected flag"
    priority: P0
    status: done
    depends_on: ["T-012", "T-013", "T-010"]
    branch: "feat/T-013-T-014-parsers-chunker-pii"
    pr_url: ""
    head_sha: "4ff9d0f205c203953b1a82631c35b30959cd8bd1"
    acceptance_criteria:
      - "Chunk size and overlap read from config table (set by spike T-010)"
      - "Each chunk inserted with embedding_status='pending'"
      - "PII scanner (spaCy PERSON + regex SSN/CC/medical) sets pii_detected=true"
      - "make scan-pii target runs scanner over WHERE pii_detected IS NULL"
      - "Scanner accuracy validated against tests/pii_test_corpus/ (50 PII / 50 clean)"
    prd_ref: "Stories 1.4, 1.7"

  - id: T-015
    title: "Embedding worker: asyncio.Task with FOR UPDATE SKIP LOCKED, retry, and failed status"
    priority: P0
    status: done
    depends_on: ["T-014"]
    branch: "feat/T-015-T-016-workers"
    pr_url: ""
    head_sha: "30d2c124a6ee7c2c501f495a0e7902992b220264"
    acceptance_criteria:
      - "Sets embedding_status='processing' atomically via FOR UPDATE SKIP LOCKED"
      - "Calls Ollama at host.docker.internal:11434 (not as Docker service)"
      - "On failure: increments retry_count; sets 'failed' after embed_retry_max (from config)"
      - "EMBED_QUEUE bounded asyncio.Queue(maxsize=500) for backpressure"
    prd_ref: "Story 1.5"

  - id: T-016
    title: "Outbox worker: asyncio.Task draining FalkorDB writes with dead-letter after 10 failures"
    priority: P0
    status: done
    depends_on: ["T-002", "T-012"]
    branch: "feat/T-015-T-016-workers"
    pr_url: ""
    head_sha: "30d2c124a6ee7c2c501f495a0e7902992b220264"
    acceptance_criteria:
      - "Polls outbox WHERE processed_at IS NULL AND NOT failed"
      - "Applies document_added, entity_deleted, person_merged events to FalkorDB"
      - "After OUTBOX_MAX_ATTEMPTS=10, sets failed=true; surfaced in TUI Dashboard"
      - "Handles :SENT (sender) and :RECEIVED (to/cc/bcc) edges correctly"
    prd_ref: "Story 1.6"

  - id: T-017
    title: "Dead-letter retry: 3 attempts with exponential backoff (2s/8s/32s)"
    priority: P1
    status: done
    depends_on: ["T-015", "T-016"]
    branch: "feat/T-017-T-018-T-019-retry-vault-tui"
    pr_url: ""
    head_sha: "91e6738fc14b34e231d71585e52a0cc1635a9155"
    acceptance_criteria:
      - "Dead letter files retried up to 3 times with 2s/8s/32s backoff"
      - "TUI Dashboard shows error count from dead_letter table"
    prd_ref: "Story 1.10"

  - id: T-018
    title: "Vault sync: write Markdown + YAML frontmatter to ./vault-sync/ (chmod 444)"
    priority: P1
    status: done
    depends_on: ["T-012", "T-013"]
    branch: "feat/T-017-T-018-T-019-retry-vault-tui"
    pr_url: ""
    head_sha: "91e6738fc14b34e231d71585e52a0cc1635a9155"
    acceptance_criteria:
      - "Writes ./vault-sync/persons/ and ./vault-sync/documents/ Markdown files"
      - "Files created with chmod 444 (read-only for Obsidian)"
      - "YAML frontmatter includes relevant metadata"
    prd_ref: "Story 1.8"

  - id: T-019
    title: "TUI: Dashboard + Intake screen + BM25 Search screen"
    priority: P1
    status: done
    depends_on: ["T-005", "T-015", "T-016"]
    branch: "feat/T-017-T-018-T-019-retry-vault-tui"
    pr_url: ""
    head_sha: "91e6738fc14b34e231d71585e52a0cc1635a9155"
    acceptance_criteria:
      - "Dashboard: service health, chunk counts (total/pending/done), error log, outbox depth"
      - "Intake: per-file status/progress/heartbeat; [D]rop [P]ause [R]etry [S]ystem-reset"
      - "Search: BM25 query against pkg-db; E opens $EDITOR; O opens $PAGER; Enter expands inline"
      - "Heartbeat alert at 120s stall (amber row + dashboard error increment)"
    prd_ref: "Story 1.9"

  # ── Epic 2: Semantic Search & Hybrid Retrieval ─────────────────────────────

  - id: T-020
    title: "FastAPI POST /search: hybrid BM25+ANN+RRF+CrossEncoder with Pydantic validation"
    priority: P1
    status: done
    depends_on: ["T-015", "T-019"]
    branch: "feat/T-020-T-021-T-022-search"
    pr_url: ""
    head_sha: "81d66bd80111dadc40fd22e60696c2633f88b628"
    acceptance_criteria:
      - "SearchRequest validates q (max_length=2000) and limit (1-100)"
      - "BM25 top 50 + ANN top 50 merged via RRF (k from config, default 60)"
      - "CrossEncoder reranker in-process via sentence-transformers (graceful degradation if unavailable)"
      - "Response includes degraded:true when reranker unavailable"
      - "LRU cache with TTL from config.search_cache_ttl"
    prd_ref: "Story 2.1"

  - id: T-021
    title: "TUI Search: hybrid results with BM25/vector/reranker score columns + degraded banner"
    priority: P1
    status: done
    depends_on: ["T-020"]
    branch: "feat/T-020-T-021-T-022-search"
    pr_url: ""
    head_sha: "81d66bd80111dadc40fd22e60696c2633f88b628"
    acceptance_criteria:
      - "Results table shows BM25 score, vector score, reranker score per result"
      - "[DEGRADED — BM25 only] banner when degraded:true in response"
      - "Settings screen shows rrf_k as read-display"
    prd_ref: "Story 2.2"

  - id: T-022
    title: "make reindex: re-embed all chunks to embedding_v2 via Alembic then atomic rename"
    priority: P2
    status: done
    depends_on: ["T-001", "T-020"]
    branch: "feat/T-020-T-021-T-022-search"
    pr_url: ""
    head_sha: "81d66bd80111dadc40fd22e60696c2633f88b628"
    acceptance_criteria:
      - "Alembic migration adds embedding_v2 VECTOR(N) column"
      - "make reindex re-embeds all chunks into embedding_v2 within 5-minute window"
      - "Atomic column rename: old embedding dropped after operator confirmation"
    prd_ref: "Story 2.3"

  # ── Epic 3: Knowledge Graph & Entity Resolution ────────────────────────────

  - id: T-030
    title: "spaCy NER: extract PERSON/ORG/GPE → Concept nodes via outbox"
    priority: P2
    status: done
    depends_on: ["T-016"]
    branch: "feat/T-030-T-031-T-032-T-033-T-034-epic3"
    pr_url: ""
    head_sha: "975873f9a82c21d1c3bccd4e5df4c3d9f4d7e210"
    acceptance_criteria:
      - "en_core_web_sm extracts entities at ingest time (deterministic, no LLM)"
      - "Each entity → (:Concept) node in FalkorDB via outbox event"
      - "valid_at = ingest timestamp; no invalid_at unless fact becomes stale"
    prd_ref: "Story 3.1"

  - id: T-031
    title: "Entity resolution spike: threshold sweep 0.80-0.99 on labeled pair set"
    priority: P2
    status: done
    depends_on: ["T-030"]
    branch: "feat/T-030-T-031-T-032-T-033-T-034-epic3"
    pr_url: ""
    head_sha: "975873f9a82c21d1c3bccd4e5df4c3d9f4d7e210"
    acceptance_criteria:
      - "Labeled set: 50 known-duplicate + 50 known-distinct person pairs in tests/"
      - "Two approaches tested: (A) Jaro-Winkler name only; (B) name + email domain + shared docs"
      - "Precision/recall curves plotted for both approaches"
      - "Canary guard: tests/canary_pairs.json lists known-distinct pairs; asserts no merged_into chain"
    prd_ref: "Stories 3.2, 3.3"

  - id: T-032
    title: "TUI Entities screen: merge queue with Jaro-Winkler evidence; manual merge only"
    priority: P2
    status: done
    depends_on: ["T-031"]
    branch: "feat/T-030-T-031-T-032-T-033-T-034-epic3"
    pr_url: ""
    head_sha: "975873f9a82c21d1c3bccd4e5df4c3d9f4d7e210"
    acceptance_criteria:
      - "Entities list with merge-candidate queue"
      - "Expanded evidence row: Jaro-Winkler score, email domain match, shared document count"
      - "[M Merge] requires second confirmation prompt — no auto-merge"
      - "Merged person sets merged_into FK and invalid_at on FalkorDB edges via outbox"
    prd_ref: "Story 3.2"

  - id: T-033
    title: "Vault sync Wikilinks from FalkorDB :MENTIONS edges"
    priority: P2
    status: done
    depends_on: ["T-018", "T-030"]
    branch: "feat/T-030-T-031-T-032-T-033-T-034-epic3"
    pr_url: ""
    head_sha: "975873f9a82c21d1c3bccd4e5df4c3d9f4d7e210"
    acceptance_criteria:
      - "Document Markdown files include [[Person/Name]] Wikilinks from :MENTIONS edges"
      - "Links update when graph edges are added/removed"
    prd_ref: "Story 3.4"

  - id: T-034
    title: "MCP server: /mcp/ endpoint with add_document, search_facts, search_nodes tools"
    priority: P2
    status: done
    depends_on: ["T-020"]
    branch: "feat/T-030-T-031-T-032-T-033-T-034-epic3"
    pr_url: ""
    head_sha: "975873f9a82c21d1c3bccd4e5df4c3d9f4d7e210"
    acceptance_criteria:
      - "MCP Python SDK mounted at /mcp/ in tui-controller FastAPI app"
      - "Tools: add_document(text, metadata), search_facts(query), search_nodes(label, property_filter)"
    prd_ref: "Story 3.5"

  # ── Epic 4: Bi-directional Sync, Auth & Privacy Hardening ─────────────────

  - id: T-040
    title: "Auth: scoped API keys per service; make rotate-keys"
    priority: P2
    status: done
    depends_on: ["T-020"]
    branch: ""
    pr_url: ""
    head_sha: ""
    acceptance_criteria:
      - "Read-only key for Obsidian plugin; read-write key for ingest-worker"
      - "Keys via Docker secrets or .env — no JWTs"
      - "make rotate-keys generates and updates keys without downtime"
    prd_ref: "Story 4.2"

  - id: T-041
    title: "Soft-delete: deleted_at on documents/persons; TUI confirmation modal"
    priority: P2
    status: done
    depends_on: ["T-019"]
    branch: ""
    pr_url: ""
    head_sha: ""
    acceptance_criteria:
      - "DELETE /entity/{id} sets deleted_at = now()"
      - "All queries filter WHERE deleted_at IS NULL"
      - "FalkorDB edges get invalid_at via outbox"
      - "TUI modal shows entity summary before confirming; two-keystroke confirmation"
    prd_ref: "Story 4.3a"

  - id: T-042
    title: "Hard delete: 30-day quarantine gate via make hard-delete --confirm"
    priority: P2
    status: done
    depends_on: ["T-041"]
    branch: ""
    pr_url: ""
    head_sha: ""
    acceptance_criteria:
      - "make hard-delete --confirm deletes rows with deleted_at < now()-30d"
      - "Chunks cascade via FK; FalkorDB DETACH DELETE via outbox"
      - "Receipt appended to ./data/deletion_log.jsonl"
    prd_ref: "Story 4.3b"

  - id: T-043
    title: "PII report: TUI Settings view with persons (pii=true) + pii_detected chunks; bulk redact"
    priority: P2
    status: done
    depends_on: ["T-041"]
    branch: ""
    pr_url: ""
    head_sha: ""
    acceptance_criteria:
      - "PII Report lists persons(pii=true) with doc counts + chunks(pii_detected=true) per doc"
      - "Operator can mark person pii=false (public figure)"
      - "Bulk-redact replaces chunk text with [REDACTED]"
    prd_ref: "Story 4.4"

  - id: T-044
    title: "TUI Settings: BM25/vector weight sliders writing to config table"
    priority: P3
    status: done
    depends_on: ["T-021"]
    branch: ""
    pr_url: ""
    head_sha: ""
    acceptance_criteria:
      - "BM25/vector sliders (0.0-1.0, sum=1.0) write to config table"
      - "/search reads weights at query time and applies weighted score fusion"
    prd_ref: "Story 4.5"

  - id: T-045
    title: "Prometheus metrics: /metrics on port 9090 (deferred, YAGNI)"
    priority: P3
    status: done
    depends_on: ["T-020"]
    branch: ""
    pr_url: ""
    head_sha: ""
    acceptance_criteria:
      - "pkg_chunks_total, pkg_ingest_latency_seconds, pkg_query_latency_seconds, pkg_outbox_depth"
      - "Optional scrape target in docker-compose.yml"
    prd_ref: "Story 4.6"

  - id: T-046
    title: "PUT /entities/{type}/{id} — bidirectional sync for Obsidian plugin"
    priority: P2
    status: done
    depends_on: ["T-041"]
    branch: "feat/T-046-T-047-put-entity-rate-limit"
    pr_url: ""
    head_sha: ""
    acceptance_criteria:
      - "PUT /entities/{type}/{id} accepts frontmatter diffs as JSON body"
      - "Conflict rule: server updated_at > client_updated_at → conflict_detected=true, server value kept"
      - "Non-conflict diffs applied atomically with outbox event for FalkorDB sync"
      - "Unknown/unsafe fields rejected with 400"
    prd_ref: "Story 4.1"

  - id: T-047
    title: "Rate limiting: slowapi 100 req/min per IP on all endpoints"
    priority: P2
    status: done
    depends_on: ["T-020"]
    branch: "feat/T-046-T-047-put-entity-rate-limit"
    pr_url: ""
    head_sha: ""
    acceptance_criteria:
      - "slowapi Limiter added to FastAPI app with default_limits=['100/minute']"
      - "RateLimitExceeded returns HTTP 429"
      - "Graceful degradation: if slowapi not installed, app starts normally without rate limiting"
    prd_ref: "PRD §3.5"
```
