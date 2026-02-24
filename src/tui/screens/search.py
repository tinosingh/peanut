"""Search screen — BM25 query with E/O/Enter key bindings."""
from __future__ import annotations

import os
import subprocess
import webbrowser
import urllib.parse
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Static


class SearchScreen(Screen):
    """Hybrid search (BM25 in Epic 1, +ANN in Epic 2).

    Key bindings:
      E  — open in Obsidian (obsidian:// URI) or $EDITOR
      O  — open raw path in $PAGER
      Enter — expand chunk inline
    """

    BINDINGS = [
        Binding("?",      "app.toggle_help", "Help"),
        Binding("escape", "app.pop_screen",  "Back"),
        Binding("e",      "open_editor",     "Open in Obsidian/$EDITOR"),
        Binding("o",      "open_raw",        "Open in $PAGER"),
        Binding("enter",  "expand_inline",   "Expand chunk"),
    ]

    DEFAULT_CSS = """
    SearchScreen { layout: vertical; }
    #search-input { dock: top; margin: 1; }
    #results-table { height: 1fr; }
    #expanded-chunk { height: 8; border: solid $primary; padding: 0 1; display: none; }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Input(placeholder="Search your documents…", id="search-input")
        yield DataTable(id="results-table", zebra_stripes=True)
        yield Static("", id="expanded-chunk")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("#", "SOURCE FILE", "SENDER", "BM25", "VEC", "RERANK")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self._run_search(event.value)

    async def _run_search(self, query: str) -> None:
        """POST /search and populate the results table."""
        import httpx
        table = self.query_one(DataTable)
        table.clear()
        try:
            api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f"{api_url}/search", json={"q": query, "limit": 10})
                resp.raise_for_status()
                data = resp.json()
            for i, result in enumerate(data.get("results", []), 1):
                table.add_row(
                    str(i),
                    result.get("source_path", ""),
                    result.get("sender", "—"),
                    f"{result.get('bm25_score', 0):.2f}",
                    f"{result.get('vector_score', 0):.2f}",
                    f"{result.get('rerank_score', 0):.2f}",
                )
            if data.get("degraded"):
                self.notify("[DEGRADED — BM25 only]", severity="warning")
        except Exception as exc:
            self.notify(f"Search error: {exc}", severity="error")

    def action_open_editor(self) -> None:
        """E key: open selected result in Obsidian or $EDITOR."""
        vault_sync = os.getenv("VAULT_SYNC_PATH", "./vault-sync")
        # Placeholder: get focused row path in full implementation
        path = ""
        if path and path.startswith(str(Path(vault_sync).resolve())):
            rel = os.path.relpath(path, vault_sync)
            vault_name = Path(vault_sync).name
            uri = f"obsidian://open?vault={vault_name}&file={urllib.parse.quote(rel)}"
            webbrowser.open(uri)
        else:
            editor = os.getenv("EDITOR", "less")
            self.run_worker([editor, path], thread=True)

    def action_open_raw(self) -> None:
        pager = os.getenv("PAGER", "less")
        self.notify(f"Open in {pager} (wired in Epic 2 integration)")

    def action_expand_inline(self) -> None:
        box = self.query_one("#expanded-chunk", Static)
        box.display = not box.display
