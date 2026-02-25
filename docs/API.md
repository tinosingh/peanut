# Peanut API Reference

## Overview

RESTful API for personal knowledge graph operations. All endpoints served by FastAPI with Textual TUI.

**Base URL:** `http://localhost:8000`

---

## Search API

### POST /search
Hybrid semantic search combining BM25 full-text and pgvector ANN with RRF merge and CrossEncoder reranking.

**Request Body:**
```json
{
  "q": "project budget review",
  "limit": 10
}
```

**Parameters:**
- `q` (string, required): Search query, 1-2000 chars
- `limit` (int, optional): Results per page, default 10

**Response:**
```json
{
  "results": [
    {
      "chunk_id": "uuid",
      "doc_id": "uuid",
      "source_path": "/drop-zone/email.mbox",
      "sender": "alice@example.com",
      "snippet": "...truncated to 200 chars...",
      "bm25_score": 0.8234,
      "vector_score": 0.6721,
      "rerank_score": 0.9145
    }
  ],
  "query": "project budget review",
  "degraded": false
}
```

**Status Codes:**
- `200 OK` — Results returned
- `400 Bad Request` — Invalid query (too short/long)
- `503 Service Unavailable` — Embedding service down

**Notes:**
- Results cached for 60 seconds (configurable)
- If Ollama unavailable, falls back to BM25-only (degraded=true)
- If CrossEncoder unavailable and results ≥5, falls back to RRF scores (degraded=true)

---

## Entities API

### GET /entities/merge-candidates
List persons eligible for merging based on entity resolution scoring.

**Response:**
```json
{
  "candidates": [
    {
      "name_a": "Alice Smith",
      "name_b": "A. Smith",
      "email_a": "alice@example.com",
      "email_b": "asmith@example.com",
      "score": 0.85
    }
  ]
}
```

### POST /entities/merge
Merge person name_b into name_a. Requires manual confirmation (M key in TUI).

**Request Parameters:**
- `name_a`: Target person
- `name_b`: Source person (will be marked as merged_into name_a)

**Response:**
```json
{
  "merged_from": "uuid-of-b",
  "merged_into": "uuid-of-a"
}
```

### POST /entities/soft-delete
Soft-delete document or person (sets deleted_at).

**Request Parameters:**
- `entity_type`: "document" or "person"
- `entity_id`: UUID

**Response:**
```json
{
  "id": "uuid",
  "entity_type": "person",
  "deleted_at": "2024-12-25T10:30:00Z"
}
```

### POST /entities/hard-delete
Permanently delete rows with deleted_at < now()-30 days (irreversible).

**Request Parameters:**
- `confirm`: Must be `true`

**Response:**
```json
{
  "documents_deleted": 42,
  "persons_deleted": 7,
  "chunks_deleted": 1250
}
```

### PUT /entities/{entity_type}/{entity_id}
Bidirectional sync for Obsidian plugin (server timestamp wins on conflict).

**Request Body:**
```json
{
  "display_name": "Alice Smith",
  "email": "alice@example.com",
  "pii": true,
  "client_ts": "2024-12-25T10:30:00Z"
}
```

**Response:**
```json
{
  "id": "uuid",
  "updated_fields": ["display_name"],
  "conflict_detected": false,
  "server_ts": "2024-12-25T10:31:00Z"
}
```

**Updatable Fields:**
- Person: display_name, email, pii
- Document: source_path

---

## Configuration API

### GET /config
Get all config values.

### PUT /config/{key}
Update config value.

---

## Metrics API

### GET /metrics
Prometheus-compatible metrics.

---

## Health Check

### GET /health
Service health.

---

## Rate Limiting

Default: 100 requests/minute per IP via slowapi.

---

## Logging

Structured logging via structlog:
- `search_started`: query, limit
- `search_completed`: result_count, elapsed_ms, degraded
- `outbox_event_processed`: event_type, latency_ms
- `embeddings_written`: count, ollama_latency_ms

---

## Error Handling

All errors return JSON with `detail` field:
```json
{
  "detail": "Person not found"
}
```

Common status codes:
- `400 Bad Request`
- `404 Not Found`
- `409 Conflict`
- `429 Too Many Requests`
- `503 Service Unavailable`
