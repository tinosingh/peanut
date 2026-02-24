.PHONY: up down reset logs tui test lint typecheck \
        migrate-up backup restore-from-backup test-backup-restore \
        sanity audit hard-delete scan-pii reindex rotate-keys help

COMPOSE        := docker compose
BACKUP_DIR     := ./data/backups
TIMESTAMP      := $(shell date +%Y%m%d_%H%M%S)
BACKUP_FILE    := $(BACKUP_DIR)/pkg_$(TIMESTAMP).sql
DB_CONTAINER   := pkg-db
DB_USER        ?= pkg
DB_NAME        ?= pkg

help:
	@echo "Personal Knowledge Graph — Makefile targets"
	@echo ""
	@echo "  up                   Start all services"
	@echo "  down                 Stop all services"
	@echo "  reset                Wipe volumes and restart"
	@echo "  logs                 Tail all service logs"
	@echo "  tui                  Open TUI in a fresh PTY"
	@echo "  test                 Run test suite"
	@echo "  lint                 ruff check"
	@echo "  migrate-up           Apply pending Alembic migrations"
	@echo "  backup               Dump Postgres to ./data/backups/"
	@echo "  restore-from-backup  Restore latest backup"
	@echo "  test-backup-restore  Full backup/restore cycle with row count assertion"
	@echo "  sanity               Check for orphaned chunks"
	@echo "  audit                Trivy image security scan"
	@echo "  hard-delete          Hard delete quarantined rows (requires --confirm)"
	@echo "  scan-pii             Run PII scanner over un-scanned chunks"
	@echo "  reindex              Re-embed all chunks to embedding_v2"

up:
	@cp -n .env.example .env 2>/dev/null || true
	$(COMPOSE) up -d
	@echo "Stack started. Run 'make logs' to follow output."

down:
	$(COMPOSE) down

reset:
	$(COMPOSE) down -v
	$(COMPOSE) up -d

logs:
	$(COMPOSE) logs -f

tui:
	@echo "Opening TUI (use Ctrl+C to exit)..."
	docker exec -it pkg-tui python -m src.tui.main

test:
	@$(COMPOSE) -f docker-compose.test.yml up -d
	@sleep 3
	POSTGRES_URL=postgresql://pkg:pkg@localhost:5433/pkg_test \
	  .venv/bin/pytest tests/ --tb=short -q
	@$(COMPOSE) -f docker-compose.test.yml down

lint:
	.venv/bin/ruff check src/ tests/

typecheck:
	.venv/bin/mypy src/ --ignore-missing-imports

migrate-up:
	POSTGRES_URL=$$($(COMPOSE) exec -T pkg-db sh -c \
	  'echo postgresql://$$POSTGRES_USER:$$POSTGRES_PASSWORD@localhost:5432/$$POSTGRES_DB') \
	  .venv/bin/alembic upgrade head

backup:
	@mkdir -p $(BACKUP_DIR)
	$(COMPOSE) exec -T $(DB_CONTAINER) \
	  pg_dump -U $(DB_USER) $(DB_NAME) > $(BACKUP_FILE)
	@echo "Backup saved: $(BACKUP_FILE)"

restore-from-backup:
	@LATEST=$$(ls -t $(BACKUP_DIR)/*.sql 2>/dev/null | head -1); \
	  if [ -z "$$LATEST" ]; then echo "No backups found in $(BACKUP_DIR)"; exit 1; fi; \
	  echo "Restoring $$LATEST ..."; \
	  $(COMPOSE) exec -T $(DB_CONTAINER) \
	    psql -U $(DB_USER) -d $(DB_NAME) < "$$LATEST"; \
	  echo "Restore complete."

test-backup-restore:
	@echo "=== Backup/restore cycle test ==="
	@ROW_COUNT_BEFORE=$$($(COMPOSE) exec -T $(DB_CONTAINER) \
	  psql -U $(DB_USER) -d $(DB_NAME) -t -c "SELECT count(*) FROM documents"); \
	  $(MAKE) backup; \
	  LATEST=$$(ls -t $(BACKUP_DIR)/*.sql | head -1); \
	  $(COMPOSE) exec -T $(DB_CONTAINER) \
	    psql -U $(DB_USER) -d $(DB_NAME) -c "TRUNCATE documents CASCADE"; \
	  $(MAKE) restore-from-backup; \
	  ROW_COUNT_AFTER=$$($(COMPOSE) exec -T $(DB_CONTAINER) \
	    psql -U $(DB_USER) -d $(DB_NAME) -t -c "SELECT count(*) FROM documents"); \
	  if [ "$$ROW_COUNT_BEFORE" = "$$ROW_COUNT_AFTER" ]; then \
	    echo "PASS: row counts match ($$ROW_COUNT_BEFORE)"; \
	  else \
	    echo "FAIL: before=$$ROW_COUNT_BEFORE after=$$ROW_COUNT_AFTER"; exit 1; \
	  fi

sanity:
	@ORPHANS=$$($(COMPOSE) exec -T $(DB_CONTAINER) \
	  psql -U $(DB_USER) -d $(DB_NAME) -t -c \
	  "SELECT count(*) FROM chunks c LEFT JOIN documents d ON c.doc_id = d.id WHERE d.id IS NULL"); \
	  if [ "$$(echo $$ORPHANS | tr -d ' ')" = "0" ]; then \
	    echo "OK: 0 orphaned chunks"; \
	  else \
	    echo "FAIL: $$ORPHANS orphaned chunks detected"; exit 1; \
	  fi

audit:
	@command -v trivy >/dev/null 2>&1 || { echo "trivy not found — install: brew install trivy"; exit 1; }
	trivy image --exit-code 1 --severity HIGH,CRITICAL \
	  $$($(COMPOSE) config --images | tr '\n' ' ')

hard-delete:
	@if [ "$(filter --confirm,$(MAKEFLAGS))" = "" ] && [ "$(CONFIRM)" != "yes" ]; then \
	  echo "ERROR: hard-delete requires --confirm flag or CONFIRM=yes"; \
	  echo "       make hard-delete CONFIRM=yes"; exit 1; fi
	@$(COMPOSE) exec -T $(DB_CONTAINER) \
	  psql -U $(DB_USER) -d $(DB_NAME) -c \
	  "DELETE FROM documents WHERE deleted_at < now() - interval '30 days'; \
	   DELETE FROM persons WHERE deleted_at < now() - interval '30 days';"
	@echo "Hard delete complete. Check ./data/deletion_log.jsonl"

scan-pii:
	$(COMPOSE) exec pkg-ingest python -m src.ingest.pii --scan-unscanned

reindex:
	$(COMPOSE) exec pkg-ingest python -m src.ingest.reindex

rotate-keys:
	@echo "Rotating API keys..."
	@NEW_KEY=$$(python3 -c "import secrets; print(secrets.token_urlsafe(32))"); \
	  sed -i.bak "s/^API_KEY=.*/API_KEY=$$NEW_KEY/" .env; \
	  echo "New API key written to .env"
