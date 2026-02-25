"""Dashboard screen — service health, chunk counts, outbox depth, error log."""
from __future__ import annotations

import os

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


class DashboardScreen(Screen):
    """Main dashboard: service health + pipeline status.

    Auto-refreshes every 10s.
    """

    BINDINGS = [
        Binding("?",      "app.toggle_help", "Help"),
        Binding("r",      "refresh_now",     "Refresh"),
        Binding("i",      "app.goto_intake", "Intake"),
        Binding("/",      "app.goto_search", "Search"),
    ]

    DEFAULT_CSS = """
    DashboardScreen { layout: vertical; }
    #header-panel { height: 3; padding: 0 1; }
    #stats-panel  { height: 6; border: solid $primary; padding: 1; }
    #errors-panel { height: 1fr; border: solid $error; padding: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("PKG  ·  Personal Knowledge Graph  ·  v0.1.0", id="header-panel")
        yield Static("Loading…", id="stats-panel")
        yield Static("No errors", id="errors-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._refresh(), thread=False)
        self.set_interval(10, self._refresh_sync)

    def _refresh_sync(self) -> None:
        self.run_worker(self._refresh(), thread=False)

    async def _refresh(self) -> None:
        import httpx
        api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        stats = self.query_one("#stats-panel", Static)
        errors = self.query_one("#errors-panel", Static)
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                health = await client.get(f"{api_url}/health")
                health.raise_for_status()
        except Exception as exc:
            stats.update(f"[ERROR] API unreachable: {exc}")
            return

        try:
            from src.shared.db import get_pool
            pool = await get_pool()
            async with pool.connection() as conn:
                chunk_rows = await (await conn.execute(
                    "SELECT embedding_status, COUNT(*) FROM chunks GROUP BY embedding_status"
                )).fetchall()
                outbox_row = await (await conn.execute(
                    "SELECT COUNT(*) FROM outbox WHERE processed_at IS NULL AND NOT failed"
                )).fetchone()
                dead_row = await (await conn.execute(
                    "SELECT COUNT(*) FROM outbox WHERE failed = true"
                )).fetchone()

            chunk_counts = {r[0]: r[1] for r in chunk_rows}
            total = sum(chunk_counts.values())
            done = chunk_counts.get("done", 0)
            pending = chunk_counts.get("pending", 0)
            failed = chunk_counts.get("failed", 0)
            outbox_depth = outbox_row[0] if outbox_row else 0
            dead_letters = dead_row[0] if dead_row else 0

            stats.update(
                f"Chunks: {total} total  |  {done} embedded  |  {pending} pending  |  {failed} failed\n"
                f"Outbox depth: {outbox_depth}  |  Dead-letters: {dead_letters}  |  API: OK"
            )
            if dead_letters > 0:
                errors.update(f"[WARNING] {dead_letters} dead-lettered outbox events — check logs")
            else:
                errors.update("No errors")
        except Exception as exc:
            stats.update(f"DB unavailable: {exc}")

    def action_refresh_now(self) -> None:
        self.run_worker(self._refresh(), thread=False)
