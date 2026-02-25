"""Intake screen — drop zone file queue with per-file status and heartbeat."""
from __future__ import annotations

import os
from datetime import UTC, datetime

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
        Binding("?",      "app.toggle_help", "Help"),
        Binding("escape", "app.pop_screen",  "Back"),
        Binding("d",      "drop_file",       "Drop file"),
        Binding("p",      "pause_watcher",   "Pause/Resume watcher"),
        Binding("r",      "retry_errors",    "Retry errors"),
        Binding("s",      "system_reset",    "System reset"),
    ]

    DEFAULT_CSS = """
    IntakeScreen { layout: vertical; }
    #title      { padding: 1; background: $panel; }
    #file-table { height: 1fr; }
    #status-bar { height: 1; }
    """

    _watcher_paused: bool = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Drop Zone Monitor — Watching: /drop-zone/", id="title")
        yield DataTable(id="file-table", zebra_stripes=True)
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("FILE", "STATUS", "PROGRESS", "HEARTBEAT", "CHUNKS")
        self.set_interval(2.0, self._refresh_table_sync)
        self.run_worker(self._refresh_table(), thread=False)

    def _refresh_table_sync(self) -> None:
        self.run_worker(self._refresh_table(), thread=False)

    async def _refresh_table(self) -> None:
        """Poll ingest-worker status from DB and update table rows."""
        try:
            from src.shared.db import get_pool
            pool = await get_pool()
            async with pool.connection() as conn:
                rows = await (await conn.execute(
                    """
                    SELECT
                        d.source_path,
                        d.ingested_at,
                        COUNT(c.id) AS chunk_count,
                        SUM(CASE WHEN c.embedding_status = 'done' THEN 1 ELSE 0 END) AS done_count,
                        SUM(CASE WHEN c.embedding_status = 'failed' THEN 1 ELSE 0 END) AS failed_count
                    FROM documents d
                    LEFT JOIN chunks c ON c.doc_id = d.id
                    WHERE d.deleted_at IS NULL
                    GROUP BY d.id, d.source_path, d.ingested_at
                    ORDER BY d.ingested_at DESC
                    LIMIT 50
                    """
                )).fetchall()

            table = self.query_one(DataTable)
            table.clear()
            now = datetime.now(UTC)
            for source_path, ingested_at, total, done, failed in rows:
                fname = source_path.split("/")[-1] if source_path else "?"
                total = total or 0
                done = done or 0
                failed = failed or 0
                if failed > 0:
                    status = "FAILED"
                elif done == total and total > 0:
                    status = "DONE"
                elif done > 0:
                    status = "EMBEDDING"
                else:
                    status = "PENDING"
                progress = f"{done}/{total}" if total else "—"
                # Heartbeat: seconds since ingest
                if ingested_at:
                    elapsed = (now - ingested_at.replace(tzinfo=UTC) if ingested_at.tzinfo is None else now - ingested_at)
                    heartbeat = f"{int(elapsed.total_seconds())}s ago"
                    if elapsed.total_seconds() > 120:
                        heartbeat = f"[WARNING] {heartbeat}"
                else:
                    heartbeat = "—"
                table.add_row(fname, status, progress, heartbeat, str(total))

        except Exception as exc:
            self.query_one("#status-bar", Static).update(f"DB error: {exc}")

    def action_drop_file(self) -> None:
        """D key: prompt for file path to copy into drop-zone."""
        drop_zone = os.getenv("DROP_ZONE_PATH", "./drop-zone")
        self.notify(
            f"Copy file to {drop_zone}/ — watcher will detect it automatically",
            severity="information",
        )

    def action_pause_watcher(self) -> None:
        """P key: toggle watcher pause (creates/removes drop-zone/.pause sentinel)."""
        drop_zone = os.getenv("DROP_ZONE_PATH", "./drop-zone")
        sentinel = os.path.join(drop_zone, ".pause")
        try:
            if self._watcher_paused:
                if os.path.exists(sentinel):
                    os.remove(sentinel)
                self._watcher_paused = False
                self.notify("Watcher resumed", severity="information")
            else:
                open(sentinel, "w").close()
                self._watcher_paused = True
                self.notify("Watcher paused — new files will not be ingested", severity="warning")
        except OSError as exc:
            self.notify(f"Pause toggle failed: {exc}", severity="error")

    def action_retry_errors(self) -> None:
        """R key: reset failed chunks to pending for retry."""
        self.run_worker(self._retry_errors(), thread=False)

    async def _retry_errors(self) -> None:
        try:
            from src.shared.db import get_pool
            pool = await get_pool()
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE chunks SET embedding_status = 'pending', retry_count = 0 "
                    "WHERE embedding_status = 'failed'"
                )
            self.notify("Failed chunks reset to pending for retry", severity="information")
        except Exception as exc:
            self.notify(f"Retry reset failed: {exc}", severity="error")


    def action_system_reset(self) -> None:
        """S key: show warning about system reset."""
        self.notify(
            "System reset: run `make reset` from the host to tear down and restart",
            severity="warning",
        )
