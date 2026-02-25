"""Entities screen — merge queue with Jaro-Winkler evidence; manual merge only."""
from __future__ import annotations

import os

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static


class EntitiesScreen(Screen):
    """Entity resolution UI with merge-candidate queue.

    Key bindings:
      M  — merge selected pair (requires second confirmation)
      R  — refresh merge queue
      E  — expand evidence row (Jaro-Winkler score, email domain, shared docs)
    """

    BINDINGS = [
        Binding("?",      "app.toggle_help", "Help"),
        Binding("escape", "app.pop_screen",  "Back"),
        Binding("m",      "merge_prompt",    "Merge (confirm)"),
        Binding("r",      "refresh_queue",   "Refresh"),
        Binding("e",      "expand_evidence", "Expand evidence"),
    ]

    DEFAULT_CSS = """
    EntitiesScreen { layout: vertical; }
    #merge-candidates { height: 1fr; }
    #evidence-panel { height: 6; border: solid $warning; padding: 0 1; display: none; }
    #status-bar { dock: bottom; height: 1; }
    """

    _pending_merge: tuple[str, str] | None = None
    _confirm_pending: bool = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield DataTable(id="merge-candidates", zebra_stripes=True)
        yield Static("", id="evidence-panel")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns(
            "PERSON A", "PERSON B",
            "JW SCORE", "EMAIL DOMAIN", "SHARED DOCS",
            "MERGE?",
        )
        self.run_worker(self._load_candidates(), thread=False)

    async def _load_candidates(self) -> None:
        """Fetch merge candidates from the API."""
        import httpx
        table = self.query_one(DataTable)
        table.clear()
        api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{api_url}/entities/merge-candidates")
                resp.raise_for_status()
                data = resp.json()
            for row in data.get("candidates", []):
                domain_match = "YES" if row.get("same_domain") else "no"
                table.add_row(
                    row.get("name_a", ""),
                    row.get("name_b", ""),
                    f"{row.get('jw_score', 0):.3f}",
                    domain_match,
                    str(row.get("shared_docs", 0)),
                    "",
                    key=f"{row.get('id_a')}:{row.get('id_b')}",
                )
        except Exception as exc:
            self.notify(f"Load error: {exc}", severity="error")

    def action_expand_evidence(self) -> None:
        panel = self.query_one("#evidence-panel", Static)
        table = self.query_one(DataTable)
        if table.cursor_row is None:
            return
        row = table.get_row_at(table.cursor_row)
        panel.update(
            f"Person A: {row[0]}  |  Person B: {row[1]}\n"
            f"Jaro-Winkler: {row[2]}  |  Same email domain: {row[3]}  |  Shared docs: {row[4]}"
        )
        panel.display = True

    def action_merge_prompt(self) -> None:
        """M key: first press arms confirmation, second press executes merge."""
        table = self.query_one(DataTable)
        if table.cursor_row is None:
            self.notify("Select a candidate first", severity="warning")
            return

        row = table.get_row_at(table.cursor_row)
        if not self._confirm_pending:
            self._confirm_pending = True
            status = self.query_one("#status-bar", Static)
            status.update(
                f"[WARNING] Merge {row[0]} → {row[1]}? Press M again to confirm, Esc to cancel."
            )
        else:
            self._confirm_pending = False
            self.run_worker(self._execute_merge(row[0], row[1]), thread=False)

    async def _execute_merge(self, name_a: str, name_b: str) -> None:
        """POST /entities/merge to execute the merge."""
        import httpx
        api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        status = self.query_one("#status-bar", Static)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{api_url}/entities/merge",
                    json={"name_a": name_a, "name_b": name_b},
                )
                resp.raise_for_status()
            self.notify(f"Merged {name_a} → {name_b}", severity="information")
            status.update("")
            await self._load_candidates()
        except Exception as exc:
            self.notify(f"Merge failed: {exc}", severity="error")
            status.update("")

    def action_refresh_queue(self) -> None:
        self.run_worker(self._load_candidates(), thread=False)

    def on_key(self, event) -> None:
        if event.key == "escape" and self._confirm_pending:
            self._confirm_pending = False
            self.query_one("#status-bar", Static).update("")
            event.prevent_default()
