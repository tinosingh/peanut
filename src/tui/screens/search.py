"""Search view — hybrid BM25 + vector + CrossEncoder."""

from __future__ import annotations

import os

import httpx
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import DataTable, Input, Static


class SearchView(Widget):
    """Hybrid search interface."""

    DEFAULT_CSS = """
    SearchView {
        background: #1c1c1e;
        height: 1fr;
        layout: vertical;
    }

    #search-input {
        margin: 1 2 0 2;
        border: solid #48484a;
    }

    #search-input:focus { border: solid #0a84ff; }

    #search-hint {
        color: #48484a;
        height: 1;
        padding: 0 2;
        margin-bottom: 1;
    }

    #results-table {
        margin: 0 2;
        height: 1fr;
        border: solid #3a3a3c;
    }

    #search-status {
        background: #2c2c2e;
        color: #636366;
        height: 1;
        padding: 0 2;
        border-top: solid #3a3a3c;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("enter", "expand", "Expand", show=True),
    ]

    _last_snippets: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search your knowledge base…", id="search-input")
        yield Static("[#48484a]↵ search  ·  enter=expand[/#48484a]", id="search-hint")
        tbl = DataTable(id="results-table", zebra_stripes=True)
        yield tbl
        yield Static("[#636666]ready[/#636666]", id="search-status")

    def on_mount(self) -> None:
        tbl = self.query_one(DataTable)
        tbl.add_columns("#", "FILE", "SENDER", "SNIPPET", "BM25", "VEC", "RERANK")

    async def on_activated(self) -> None:
        self.query_one("#search-input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        self.query_one("#search-status", Static).update("[#0a84ff]searching…[/#0a84ff]")
        self.run_worker(self._search(query), exclusive=True)

    async def _search(self, query: str) -> None:
        try:
            base = f"http://localhost:{os.getenv('API_PORT', '8000')}"
            headers = {}
            key = os.getenv("API_KEY_READ", "")
            if key:
                headers["X-API-Key"] = key

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{base}/search",
                    json={"q": query, "limit": 20},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            results = data.get("results", [])
            degraded = data.get("degraded", False)

            tbl = self.query_one(DataTable)
            tbl.clear()
            self._last_snippets.clear()

            for i, r in enumerate(results, 1):
                fname = (r.get("source_path") or "").split("/")[-1] or "?"
                sender = r.get("sender") or "—"
                snippet = (r.get("snippet") or "")[:60].replace("\n", " ")
                bm25 = f"{r.get('bm25_score', 0):.3f}"
                vec = f"{r.get('vector_score', 0):.3f}"
                rerank = f"{r.get('rerank_score', 0):.3f}"
                self._last_snippets[str(i)] = r.get("snippet", "")
                tbl.add_row(
                    str(i), fname, sender, snippet, bm25, vec, rerank, key=str(i)
                )

            suffix = "  [#ff9f0a]· degraded (BM25 only)[/#ff9f0a]" if degraded else ""
            self.query_one("#search-status", Static).update(
                f"[#636366]{len(results)} results{suffix}[/#636366]"
            )
        except Exception as exc:
            self.query_one("#search-status", Static).update(f"[#ff453a]{exc}[/#ff453a]")

    def action_expand(self) -> None:
        tbl = self.query_one(DataTable)
        if tbl.cursor_row < 0:
            return
        idx = str(tbl.cursor_row + 1)
        snippet = self._last_snippets.get(idx, "")
        self.notify(f"{snippet[:100]}…", severity="information")
