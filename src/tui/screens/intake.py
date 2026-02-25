"""Intake view — drop-zone file queue with per-file ingest progress."""
from __future__ import annotations

import os
from datetime import UTC, datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import DataTable, Static


class IntakeView(Widget):
    """Live file ingestion monitor."""

    DEFAULT_CSS = """
    IntakeView {
        background: #1c1c1e;
        height: 1fr;
        layout: vertical;
    }

    #intake-header {
        background: #2c2c2e;
        color: #8e8e93;
        height: 1;
        padding: 0 2;
        border-bottom: solid #3a3a3c;
    }

    #file-table {
        height: 1fr;
        margin: 1 2;
        border: solid #3a3a3c;
    }

    #intake-status {
        background: #2c2c2e;
        color: #636366;
        height: 1;
        padding: 0 2;
        border-top: solid #3a3a3c;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("p", "pause", "Pause / Resume"),
        Binding("r", "retry", "Retry failed"),
        Binding("R", "refresh", "Refresh", show=False),
    ]

    _paused: bool = False

    def compose(self) -> ComposeResult:
        drop_zone = os.getenv("DROP_ZONE_PATH", "/drop-zone")
        yield Static(f"[#8e8e93]watching[/#8e8e93]  [bold #f2f2f7]{drop_zone}[/bold #f2f2f7]", id="intake-header")
        yield DataTable(id="file-table", zebra_stripes=True)
        yield Static("", id="intake-status")

    def on_mount(self) -> None:
        tbl = self.query_one(DataTable)
        tbl.add_columns("FILE", "TYPE", "STATUS", "PROGRESS", "AGE", "CHUNKS")
        self.set_interval(3.0, self._refresh_sync)
        self.run_worker(self._load(), exclusive=True)

    async def on_activated(self) -> None:
        await self._load()

    def _refresh_sync(self) -> None:
        self.run_worker(self._load(), exclusive=True)

    def action_refresh(self) -> None:
        self.run_worker(self._load(), exclusive=True)

    async def _load(self) -> None:
        try:
            from src.shared.db import get_pool
            pool = await get_pool()
            async with pool.connection() as conn:
                rows = await (await conn.execute(
                    "SELECT d.source_path, d.source_type, d.ingested_at, "
                    "COUNT(c.id) AS total, "
                    "SUM(CASE WHEN c.embedding_status = 'done' THEN 1 ELSE 0 END) AS done, "
                    "SUM(CASE WHEN c.embedding_status = 'failed' THEN 1 ELSE 0 END) AS failed "
                    "FROM documents d LEFT JOIN chunks c ON c.doc_id = d.id "
                    "WHERE d.deleted_at IS NULL GROUP BY d.id, d.source_path, d.source_type, d.ingested_at "
                    "ORDER BY d.ingested_at DESC LIMIT 100"
                )).fetchall()

            tbl = self.query_one(DataTable)
            tbl.clear()
            now = datetime.now(UTC)

            for source_path, source_type, ingested_at, total, done, failed in rows:
                fname = (source_path or "?").split("/")[-1]
                total = total or 0
                done = done or 0
                failed = failed or 0

                if failed > 0:
                    status = "[#ff453a]FAILED[/#ff453a]"
                elif done == total and total > 0:
                    status = "[#30d158]DONE[/#30d158]"
                elif done > 0:
                    status = "[#0a84ff]EMBEDDING[/#0a84ff]"
                else:
                    status = "[#636366]PENDING[/#636366]"

                progress = f"{done}/{total}" if total else "—"

                if ingested_at:
                    tz = ingested_at.tzinfo
                    ts = ingested_at if tz else ingested_at.replace(tzinfo=UTC)
                    elapsed = int((now - ts).total_seconds())
                    if elapsed < 60:
                        age = f"{elapsed}s"
                    elif elapsed < 3600:
                        age = f"{elapsed // 60}m"
                    else:
                        age = f"{elapsed // 3600}h"
                    if elapsed > 120 and done < total:
                        age = f"[#ff9f0a]{age}[/#ff9f0a]"
                    else:
                        age = f"[#636366]{age}[/#636366]"
                else:
                    age = "—"

                ftype = (source_type or "—").upper()
                tbl.add_row(fname, ftype, status, progress, age, str(total))

            self.query_one("#intake-status", Static).update(
                f"[#636366]{len(rows)} files  ·  p=pause  r=retry[/#636366]"
            )

        except Exception as exc:
            self.query_one("#intake-status", Static).update(f"[#ff453a]{exc}[/#ff453a]")

    def action_pause(self) -> None:
        drop_zone = os.getenv("DROP_ZONE_PATH", "/drop-zone")
        sentinel = os.path.join(drop_zone, ".pause")
        try:
            if self._paused:
                if os.path.exists(sentinel):
                    os.remove(sentinel)
                self._paused = False
                self.notify("Watcher resumed", severity="information")
            else:
                open(sentinel, "w").close()
                self._paused = True
                self.notify("Watcher paused", severity="warning")
        except OSError as exc:
            self.notify(f"Failed: {exc}", severity="error")

    def action_retry(self) -> None:
        self.run_worker(self._retry(), exclusive=False)

    async def _retry(self) -> None:
        try:
            from src.shared.db import get_pool
            pool = await get_pool()
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE chunks SET embedding_status = 'pending', retry_count = 0 "
                    "WHERE embedding_status = 'failed'"
                )
            self.notify("Failed chunks queued for retry", severity="information")
            await self._load()
        except Exception as exc:
            self.notify(f"Retry failed: {exc}", severity="error")
