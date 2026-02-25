"""Entities view — manual entity resolution / merge queue."""
from __future__ import annotations

import os

import httpx
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import DataTable, Static


class EntitiesView(Widget):
    """Merge candidate queue with Jaro-Winkler evidence."""

    DEFAULT_CSS = """
    EntitiesView {
        background: #1c1c1e;
        height: 1fr;
        layout: vertical;
    }

    #merge-label {
        color: #636366;
        text-style: bold;
        height: 1;
        padding: 0 2;
        margin-top: 1;
        background: #1c1c1e;
    }

    #merge-table {
        margin: 0 2;
        height: 1fr;
        border: solid #3a3a3c;
    }

    #entities-status {
        background: #2c2c2e;
        color: #636366;
        height: 1;
        padding: 0 2;
        border-top: solid #3a3a3c;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("m", "merge", "Merge (confirm twice)"),
        Binding("r", "reload", "Reload"),
    ]

    _candidates: list[dict] = []
    _merge_armed: bool = False
    _armed_row: int = -1

    def compose(self) -> ComposeResult:
        yield Static("MERGE CANDIDATES", id="merge-label")
        yield DataTable(id="merge-table", zebra_stripes=True)
        yield Static("[#636666]loading…[/#636666]", id="entities-status")

    def on_mount(self) -> None:
        tbl = self.query_one(DataTable)
        tbl.add_columns("PERSON A", "PERSON B", "JW SCORE", "SAME DOMAIN", "SHARED DOCS")
        self.run_worker(self._load(), exclusive=True)

    async def on_activated(self) -> None:
        await self._load()

    def action_reload(self) -> None:
        self._merge_armed = False
        self._armed_row = -1
        self.run_worker(self._load(), exclusive=True)

    async def _load(self) -> None:
        try:
            base = f"http://localhost:{os.getenv('API_PORT', '8000')}"
            headers = {}
            key = os.getenv("API_KEY_READ", "")
            if key:
                headers["X-API-Key"] = key

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{base}/entities/merge-candidates", headers=headers)
                resp.raise_for_status()
                data = resp.json()

            self._candidates = data.get("candidates", [])
            tbl = self.query_one(DataTable)
            tbl.clear()

            for c in self._candidates:
                jw = f"{c.get('jw_score', 0):.3f}"
                dom = "[#30d158]yes[/#30d158]" if c.get("same_domain") else "[#636366]no[/#636366]"
                docs = str(c.get("shared_docs", 0))
                tbl.add_row(c.get("name_a", "?"), c.get("name_b", "?"), jw, dom, docs)

            self.query_one("#entities-status", Static).update(
                f"[#636366]{len(self._candidates)} candidates  ·  m=merge  r=reload[/#636366]"
            )
        except Exception as exc:
            self.query_one("#entities-status", Static).update(f"[#ff453a]{exc}[/#ff453a]")

    def action_merge(self) -> None:
        tbl = self.query_one(DataTable)
        row = tbl.cursor_row
        if row < 0 or row >= len(self._candidates):
            return
        if not self._merge_armed or self._armed_row != row:
            self._merge_armed = True
            self._armed_row = row
            c = self._candidates[row]
            self.query_one("#entities-status", Static).update(
                f"[#ff9f0a]⚠  merge {c.get('name_a')} → {c.get('name_b')}?  press m again[/#ff9f0a]"
            )
            return
        self._merge_armed = False
        self.run_worker(self._execute_merge(row), exclusive=False)

    async def _execute_merge(self, row: int) -> None:
        if row >= len(self._candidates):
            return
        c = self._candidates[row]
        try:
            base = f"http://localhost:{os.getenv('API_PORT', '8000')}"
            headers = {}
            key = os.getenv("API_KEY_WRITE", "")
            if key:
                headers["X-API-Key"] = key

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{base}/entities/merge",
                    json={"name_a": c.get("name_a"), "name_b": c.get("name_b")},
                    headers=headers,
                )
                resp.raise_for_status()

            self.notify(f"Merged {c.get('name_a')} → {c.get('name_b')}", severity="information")
            await self._load()
        except Exception as exc:
            self.notify(f"Merge failed: {exc}", severity="error")
