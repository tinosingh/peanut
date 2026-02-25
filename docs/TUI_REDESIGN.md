# Apple UX TUI Redesign

## Philosophy

The redesigned Textual TUI follows **Apple Design System** principles:

- **Clarity**: Dark mode with high contrast; every widget has a clear purpose
- **Depth**: Layered color scheme (#1c1c1e background, #2c2c2e panels, #f2f2f7 text)
- **Focus**: Keyboard-first workflow with mnemonics (1–6 for tabs, ctrl+h for help)
- **Delight**: Metric cards with color-coded status; smooth transitions

## Architecture

### Tab-Based Navigation

Six main tabs replace the previous screen stack:

```
┌─────────────────────────────────────┐
│  PKG                      [clock]   │ Header + Clock
├─────────────────────────────────────┤
│ Dashboard │ Intake │ Search │ Entities │ Settings │ Graph │
├─────────────────────────────────────┤
│                                       │ Active tab content
│             [Main content area]      │ (height: 1fr)
│                                       │
├─────────────────────────────────────┤
│ [Status bar, 1 line]                │ Footer with context
└─────────────────────────────────────┘
```

### Global Key Bindings

| Key | Action |
|---|---|
| `1–6` | Switch to Dashboard, Intake, Search, Entities, Settings, Graph |
| `ctrl+h` | Show help overlay |
| `q` | Quit |

## Screens

### 1. Dashboard (Default)

**Purpose**: System health + pipeline status at a glance

**Content**:
- Health bar (top): Postgres ● Graph ● · embedded count
- Metric cards (4 columns):
  - Embedded (green if > 0)
  - Pending (orange if > 0)
  - Outbox (orange if > 10)
  - Dead letters (red if > 0)
- Pipeline table (searchable):
  - Embedding progress %
  - Failed chunks count
  - Outbox pending count
  - Dead-letter count
- Status bar (bottom): last refresh time

**Bindings**:
- `r` – Refresh now

**Data source**: PostgreSQL queries for chunk status + outbox depth

---

### 2. Intake

**Purpose**: Live file ingest progress monitor

**Content**:
- Header: "watching /drop-zone/"
- File table (6 columns):
  - FILE: filename
  - TYPE: .mbox, .pdf, .md, etc.
  - STATUS: PENDING, EMBEDDING, DONE, FAILED (color-coded)
  - PROGRESS: done/total chunks
  - AGE: seconds/minutes/hours since ingest (orange warning if > 120s)
  - CHUNKS: total count
- Status bar: "{N} files  ·  p=pause  r=retry"

**Bindings**:
- `p` – Pause/Resume watcher (creates/removes .pause sentinel)
- `r` – Retry failed chunks (sets embedding_status = pending, retry_count = 0)

**Refresh**: Every 3 seconds

**Data source**: Documents + chunks table, grouped by doc_id

---

### 3. Search

**Purpose**: Hybrid BM25 + vector + CrossEncoder search

**Content**:
- Search input (top): "Search your knowledge base…"
- Results table (7 columns):
  - #: Result index
  - FILE: source_path
  - SENDER: persons.email (from metadata.sender_email)
  - SNIPPET: first 60 chars of chunk
  - BM25: relevance score (4 decimals)
  - VEC: vector similarity (4 decimals)
  - RERANK: CrossEncoder score (4 decimals)
- Status bar: "{N} results" + degraded warning if vector/rerank unavailable

**Bindings**:
- `↵` – Execute search (on input submission)
- `enter` – Expand snippet for selected result

**Data source**: POST /search endpoint

**Pipeline**:
1. BM25 search on tsv column
2. ANN vector search via pgvector
3. RRF merge (Reciprocal Rank Fusion with k=60) or weighted merge (configurable)
4. CrossEncoder rerank (graceful fallback if unavailable)

---

### 4. Entities

**Purpose**: Manual entity resolution / merge queue

**Content**:
- Title: "MERGE CANDIDATES"
- Candidates table (5 columns):
  - PERSON A: display_name
  - PERSON B: display_name
  - JW SCORE: Jaro-Winkler similarity (3 decimals)
  - SAME DOMAIN: "yes" or "no" (green/gray)
  - SHARED DOCS: count of documents sent by both
- Status bar: "{N} candidates  ·  m=merge  r=reload"

**Bindings**:
- `m` – Merge (two-stage confirmation):
  - First press: arm confirmation, show warning in status bar
  - Second press: execute merge via POST /entities/merge
  - Press escape to cancel
- `r` – Reload candidates

**Data source**: GET /entities/merge-candidates endpoint

**Merge logic**:
- Threshold: 0.85 Jaro-Winkler
- Atomic transaction: UPDATE persons SET merged_into, INSERT outbox event

---

### 5. Settings

**Purpose**: Runtime configuration + PII management

**Content**:
- Search weights section (editable inputs):
  - BM25 weight: 0.0–1.0 (default 0.5)
  - Vector weight: 0.0–1.0 (default 0.5)
  - Config info (read-only): rrf_k, chunk_size, embed_model
- PII report section:
  - Table (4 columns):
    - TYPE: "PERSON" or "CHUNK"
    - NAME / EXCERPT: display_name or text[:60]
    - FLAG: "pii=true" or "pii_detected"
    - DOCS: doc_count or doc_id[:8]
- Status bar: "{N} PII items  ·  s=save  p=pii  R=redact"

**Bindings**:
- `s` – Save weight changes (POST /config)
- `p` – Load PII report (GET /pii/report)
- `R` – Bulk redact (POST /pii/bulk-redact)

**Data sources**: GET /config, GET /pii/report, POST endpoints

---

### 6. Graph

**Purpose**: FalkorDB knowledge graph navigation with drill-down

**Content**:
- Header: "Knowledge Graph" or current root email
- Tree widget (hierarchical):
  - Root: "PKG" or drilling root
  - Children: Person nodes (cyan, #64d2ff)
  - Grandchildren: Document/Concept nodes (green/orange, #30d158/#ff9f0a)
  - Labels: edge types inline (e.g., "sent → Document  [created_at]")
- Status bar: "{N} edges  ·  enter=drill  backspace=back  r=reload"

**Bindings**:
- `enter` – Drill into selected node (set as new root, push to history)
- `backspace` – Go back (pop from history)
- `r` – Reload from FalkorDB

**Data source**: FalkorDB Cypher queries via `falkordb` SDK

**Queries**:
- Rooted: `MATCH (p:Person {email: $email})-[r]->(n) RETURN ... LIMIT 50`
- Global: `MATCH (a)-[r]->(b) RETURN ... LIMIT 100`

---

### 7. Help (Modal Overlay)

**Purpose**: Quick reference for all key bindings

**Content**:
- Modal dialog centered on screen
- Grouped key bindings by screen (GLOBAL, DASHBOARD, INTAKE, SEARCH, ENTITIES, SETTINGS, GRAPH)
- Blue accent color (#0a84ff) for keys
- Close button + Esc / ctrl+h to dismiss

---

## Color Palette

| Purpose | Color | Usage |
|---|---|---|
| Background | #1c1c1e | Screen background |
| Panel | #2c2c2e | Cards, inputs, tables |
| Text | #f2f2f7 | Primary text |
| Muted | #636366 | Labels, secondary text |
| Dim | #48484a | Placeholders, hints |
| Success | #30d158 | Status OK, green progress |
| Warning | #ff9f0a | Pending, >120s old |
| Error | #ff453a | Failed status |
| Info | #0a84ff | Metric values, bindings |
| Node: Person | #64d2ff | Graph person nodes |
| Node: Document | #30d158 | Graph document nodes |
| Node: Concept | #ff9f0a | Graph concept nodes |

---

## Styling Notes

### Metric Cards

Large, readable numbers with labels:
```
[bold #30d158]1,234[/bold #30d158]
[#636366]embedded[/#636366]
```

### Status Indicators

Color-coded + text:
- `[#30d158]DONE[/#30d158]` – green
- `[#ff9f0a]PENDING[/#ff9f0a]` – orange
- `[#ff453a]FAILED[/#ff453a]` – red
- `[#0a84ff]EMBEDDING[/#0a84ff]` – blue

### Table Headers

Muted color (#8e8e93) with bold text.

---

## Implementation Details

### Widget Hierarchy

```
PKGApp
├── Header (show_clock=True)
└── TabbedContent
    ├── TabPane(Dashboard) → DashboardView
    ├── TabPane(Intake) → IntakeView
    ├── TabPane(Search) → SearchView
    ├── TabPane(Entities) → EntitiesView
    ├── TabPane(Settings) → SettingsView
    └── TabPane(Graph) → GraphView
```

Each View is a `Widget` subclass with:
- `on_mount()` – Set up data refresh intervals
- `on_activated()` – Hook called when tab is switched
- `action_*()` – Handlers for key bindings
- `async _load()` – Fetch data from API/DB

### Data Refresh Strategy

- Dashboard: 30s interval
- Intake: 3s interval (live monitoring)
- Others: On-demand via actions or tab activation

### API Integration

All views call HTTP endpoints via `httpx.AsyncClient`:
- Read endpoints: `X-API-Key` from env var `API_KEY_READ`
- Write endpoints: `X-API-Key` from env var `API_KEY_WRITE`

Error handling:
- Try/except around all HTTP calls
- Notify user with severity ("information", "warning", "error")
- Update status bar with error message

---

## Tools & Quality

### Linting

- **ruff**: Syntax, imports, unused variables
- **black**: Code formatting (88-char line length)
- **isort**: Import sorting
- **mypy**: Type checking

All checks pass:
```bash
ruff check src/tui/ --select E,F --ignore E501
black --check src/tui/
isort --check-only src/tui/
mypy src/tui/screens/intake.py src/tui/screens/graph.py --ignore-missing-imports
```

### Type Annotations

Full type hints for:
- Method parameters and return types
- Widget properties
- Data structures (Dict, List, Optional)

### Python Compatibility

- Python 3.10+ (uses `timezone.utc` not `datetime.UTC`)
- All async/await properly handled
- No blocking operations in UI thread

---

## Future Enhancements

1. **Persistence**: Remember last active tab across sessions
2. **Search history**: Cache recent queries
3. **Keyboard shortcuts**: Alt+E for entity merge, etc.
4. **Notifications**: Toast alerts for ingest completion
5. **Export**: Copy search results to clipboard
6. **Dark/Light mode toggle**: Implement light theme variant
7. **Custom theme**: Load color schemes from config
8. **Graph animations**: Animate node expansion
9. **Search filters**: Add date range, document type filters
10. **Merge undo**: 24-hour rollback window for merges

