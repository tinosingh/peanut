# Peanut — Product Requirements Document

See full PRD: [knowledge-base-prd-v3.2_1.md](knowledge-base-prd-v3.2_1.md)

## Summary

A self-hosted, containerised personal knowledge system (Postgres + pgvector + FalkorDB + Ollama + Textual TUI + Docker).

**Target persona:** Technical solo operator, privacy-first, local inference preferred.

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.12 |
| TUI | Textual 8.x |
| API | FastAPI |
| Relational DB | Postgres 17 + pgvector 0.8.1 |
| Graph DB | FalkorDB v4.14.9 |
| Embeddings | Ollama `nomic-embed-text` (runs on **host**, not Docker) |
| Reranker | CrossEncoder `ms-marco-MiniLM-L6-v2` (in-process) |
| Migrations | Alembic |
| Testing | pytest + pytest-asyncio |
| Lint | ruff |

## Epics

| Epic | Goal | Sprint |
|------|------|--------|
| 0 — Infrastructure Bootstrap | One command brings up full stack; TUI shows green | Sprint 0 |
| 1 — Data Intake & Lexical Search | MBOX/PDF/MD ingest → BM25 search → Obsidian vault | Sprints 1–2 |
| 2 — Semantic Search | Hybrid BM25+ANN+RRF+CrossEncoder retrieval | Sprints 3–4 |
| 3 — Knowledge Graph & Entity Resolution | FalkorDB graph, NER, Jaro-Winkler entity merge | Sprints 5–6 |
| 4 — Bi-directional Sync, Auth & Privacy | Obsidian plugin, API keys, soft/hard delete, PII | Sprints 7–8 |

## Riskiest Assumptions

1. Ollama `nomic-embed-text` p95 embedding latency ≤ 3s (validated in Story 1.0 spike)
2. BM25 raw text search finds known emails in < 5s (validated in Story 1.0 spike)
3. Obsidian vault sync won't corrupt vault (manual destructive test at end of Epic 2)
4. TUI reduces friction enough for consistent daily use (30-day self-usage review)
