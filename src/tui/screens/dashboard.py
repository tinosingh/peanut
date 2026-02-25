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
            error_lines = []
            if dead_letters > 0:
                error_lines.append(f"[WARNING] {dead_letters} dead-lettered outbox events — check logs")

            # Canary guard: check for incorrectly merged known-distinct person pairs (Story 3.3)
            canary_violations = await _check_canary_guard(pool)
            if canary_violations:
                error_lines.append(
                    f"[CANARY VIOLATION] {len(canary_violations)} known-distinct pairs share merged_into — "
                    "entity resolution is broken. Check threshold."
                )

            errors.update("\n".join(error_lines) if error_lines else "No errors")
        except Exception as exc:
            stats.update(f"DB unavailable: {exc}")

    def action_refresh_now(self) -> None:
        self.run_worker(self._refresh(), thread=False)


async def _check_canary_guard(pool) -> list[dict]:
    """Return canary pairs that violate the known-distinct invariant (Story 3.3).

    Reads tests/canary_pairs.json. For each known-distinct pair (name_a, name_b),
    checks if either person has a merged_into FK pointing to the other — which would
    mean the resolution algorithm merged people it should not have.
    """
    import json
    from pathlib import Path

    canary_path = Path(__file__).parent.parent.parent.parent / "tests" / "canary_pairs.json"
    if not canary_path.exists():
        return []

    try:
        pairs = json.loads(canary_path.read_text())
    except Exception:
        return []

    violations = []
    try:
        async with pool.connection() as conn:
            for pair in pairs:
                name_a = pair.get("name_a", "")
                name_b = pair.get("name_b", "")
                if not name_a or not name_b:
                    continue
                row = await (await conn.execute(
                    """
                    SELECT a.id, a.merged_into, b.id AS b_id
                    FROM persons a
                    JOIN persons b ON b.display_name = %s
                    WHERE a.display_name = %s
                      AND (a.merged_into = b.id OR b.merged_into = a.id)
                    LIMIT 1
                    """,
                    (name_b, name_a),
                )).fetchone()
                if row:
                    violations.append({"name_a": name_a, "name_b": name_b})
    except Exception:
        pass

    return violations
