"""Dashboard view — system health + pipeline metrics."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import DataTable, Static

from src.tui.app import MetricCard


class DashboardView(Widget):
    """Main dashboard: metric cards + pipeline table."""

    DEFAULT_CSS = """
    DashboardView {
        background: #1c1c1e;
        height: 1fr;
        layout: vertical;
    }

    #health-bar {
        background: #2c2c2e;
        color: #636366;
        height: 1;
        padding: 0 2;
        border-bottom: solid #3a3a3c;
    }

    .metric-row {
        layout: horizontal;
        height: 9;
        margin: 1 2;
    }

    #pipeline-table {
        margin: 0 2;
        height: 1fr;
        border: solid #3a3a3c;
    }

    #pipeline-label {
        color: #636366;
        text-style: bold;
        height: 1;
        padding: 0 2;
        margin-top: 1;
        background: #1c1c1e;
    }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Static("", id="health-bar")
        yield Static("METRICS", id="pipeline-label")
        with Static(classes="metric-row"):
            yield MetricCard("embedded", "—", id="m-embedded")
            yield MetricCard("pending", "—", id="m-pending")
            yield MetricCard("outbox", "—", id="m-outbox")
            yield MetricCard("dead letters", "—", id="m-dead")
        yield Static("PIPELINE", id="pipeline-data-label")
        tbl = DataTable(id="pipeline-table", show_cursor=False)
        yield tbl
        yield Static("", id="status-bar", classes="status-bar")

    def on_mount(self) -> None:
        tbl = self.query_one("#pipeline-table", DataTable)
        tbl.add_columns("CHECK", "STATUS", "DETAIL")
        self.set_interval(30.0, self._refresh_sync)
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
                rows = await (
                    await conn.execute(
                        "SELECT embedding_status, COUNT(*) FROM chunks GROUP BY embedding_status"
                    )
                ).fetchall()
                outbox = await (
                    await conn.execute(
                        "SELECT COUNT(*) FROM outbox WHERE processed_at IS NULL AND NOT failed"
                    )
                ).fetchone()
                dead = await (
                    await conn.execute(
                        "SELECT COUNT(*) FROM outbox WHERE failed = true"
                    )
                ).fetchone()

            counts = {r[0]: r[1] for r in rows}
            embedded = counts.get("done", 0)
            pending = counts.get("pending", 0)
            failed = counts.get("failed", 0)
            outbox_n = outbox[0] if outbox else 0
            dead_n = dead[0] if dead else 0
            total = sum(counts.values()) or 1

            self.query_one("#m-embedded", MetricCard).update_metric(
                f"{embedded:,}", "#30d158" if embedded > 0 else "#636366"
            )
            self.query_one("#m-pending", MetricCard).update_metric(
                f"{pending:,}", "#ff9f0a" if pending > 0 else "#636366"
            )
            self.query_one("#m-outbox", MetricCard).update_metric(
                f"{outbox_n:,}", "#ff9f0a" if outbox_n > 10 else "#636366"
            )
            self.query_one("#m-dead", MetricCard).update_metric(
                f"{dead_n:,}", "#ff453a" if dead_n > 0 else "#636366"
            )

            try:
                import os
                import socket

                fk_host = os.getenv("FALKORDB_HOST", "pkg-graph")
                fk_port = int(os.getenv("FALKORDB_PORT", "6379"))
                with socket.create_connection((fk_host, fk_port), timeout=1):
                    graph_ok = True
            except Exception:
                graph_ok = False

            pg_badge = "[#30d158]● postgres[/#30d158]"
            graph_badge = (
                "[#30d158]● graph[/#30d158]"
                if graph_ok
                else "[#ff453a]● graph[/#ff453a]"
            )
            self.query_one("#health-bar", Static).update(
                f"{pg_badge}  {graph_badge}  [#636366]·  {embedded:,} embedded[/#636366]"
            )

            tbl = self.query_one("#pipeline-table", DataTable)
            tbl.clear()
            pct = (embedded / total * 100) if total else 0
            tbl.add_row(
                "Embedding",
                f"[#30d158]{pct:.0f}%[/#30d158]",
                f"{embedded:,} / {total:,} chunks",
            )
            tbl.add_row(
                "Failed",
                f"[#ff453a]{failed:,}[/#ff453a]" if failed else "[#636366]0[/#636366]",
                "chunks",
            )
            tbl.add_row(
                "Outbox",
                (
                    f"[#ff9f0a]{outbox_n:,}[/#ff9f0a]"
                    if outbox_n
                    else "[#636366]0[/#636366]"
                ),
                "pending",
            )
            tbl.add_row(
                "Dead Letter",
                f"[#ff453a]{dead_n:,}[/#ff453a]" if dead_n else "[#636366]0[/#636366]",
                "failed",
            )

            self.query_one("#status-bar", Static).update(
                "[#636366]last refresh: just now  ·  press r[/#636366]"
            )

        except Exception as exc:
            self.query_one("#status-bar", Static).update(
                f"[#ff453a]error: {exc}[/#ff453a]"
            )
