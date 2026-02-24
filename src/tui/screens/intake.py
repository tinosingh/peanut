"""Intake screen — drop zone file queue with per-file status and heartbeat."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static


class IntakeScreen(Screen):
    """Monitors the drop-zone file queue.

    Columns: FILE | STATUS | PROGRESS | HEARTBEAT | CHUNKS
    Bindings: D=drop, P=pause/resume, R=retry errors, S=system reset
    """

    BINDINGS = [
        Binding("?", "app.toggle_help", "Help"),
        Binding("d", "drop_file",    "Drop file"),
        Binding("p", "pause_watcher","Pause/Resume watcher"),
        Binding("r", "retry_errors", "Retry errors"),
        Binding("s", "system_reset", "System reset"),
    ]

    DEFAULT_CSS = """
    IntakeScreen { layout: vertical; }
    #title    { padding: 1; background: $panel; }
    #file-table { height: 1fr; }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("📥 Drop Zone Monitor — Watching: /drop-zone/", id="title")
        yield DataTable(id="file-table", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("FILE", "STATUS", "PROGRESS", "HEARTBEAT", "CHUNKS")
        self.set_interval(2.0, self._refresh_table)

    async def _refresh_table(self) -> None:
        """Poll ingest-worker status and update table rows."""
        # Populated in Epic 1 integration (T-019 full wiring)
        pass

    def action_drop_file(self) -> None:
        self.notify("Drop file (Epic 1 integration)")

    def action_pause_watcher(self) -> None:
        self.notify("Pause/resume watcher (Epic 1 integration)")

    def action_retry_errors(self) -> None:
        self.notify("Retry errors triggered")

    def action_system_reset(self) -> None:
        self.notify("System reset (docker compose down -v + up)")
