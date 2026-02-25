"""PKG — Personal Knowledge Graph TUI. Apple-inspired redesign."""

from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path

import structlog
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Static, TabbedContent, TabPane

log = structlog.get_logger()

THEME = """
Screen, PKGApp {
    background: #1c1c1e;
}

Tabs {
    background: #1c1c1e;
    height: 3;
    padding: 0 1;
    border-bottom: solid #3a3a3c;
}

Tabs > Tab {
    background: #1c1c1e;
    color: #636366;
    padding: 0 3;
    border: none;
    margin: 0;
}

Tabs > Tab:hover  { color: #aeaeb2; background: #242426; }

Tabs > Tab.-active {
    color: #f2f2f7;
    background: #1c1c1e;
    border-bottom: tall #0a84ff;
    text-style: bold;
}

Tabs > Underline { background: #3a3a3c; color: #3a3a3c; }

TabPane { padding: 0; background: #1c1c1e; }

DataTable {
    background: #1c1c1e;
    border: none;
    height: 1fr;
}

DataTable > .datatable--header   { background: #2c2c2e; color: #8e8e93; text-style: bold; }
DataTable > .datatable--cursor   { background: #0a3d6b; color: #f2f2f7; }
DataTable > .datatable--odd-row  { background: #1c1c1e; }
DataTable > .datatable--even-row { background: #222224; }

Input {
    background: #2c2c2e;
    border: solid #48484a;
    color: #f2f2f7;
    height: 3;
    padding: 0 1;
}

Input:focus        { border: solid #0a84ff; }
Input>.input--placeholder { color: #48484a; }

.metric-row {
    layout: horizontal;
    height: 9;
    margin: 1 2;
}

MetricCard {
    background: #2c2c2e;
    border: solid #3a3a3c;
    padding: 1 2;
    margin: 0 1 0 0;
    width: 1fr;
    height: 9;
    content-align: center middle;
}

MetricCard:last-of-type { margin-right: 0; }

.section-label {
    color: #636366;
    text-style: bold;
    height: 1;
    padding: 0 2;
    margin-top: 1;
    background: #1c1c1e;
}

.divider { background: #3a3a3c; height: 1; margin: 0 2; }

.status-bar {
    background: #2c2c2e;
    color: #636366;
    height: 1;
    padding: 0 2;
    border-top: solid #3a3a3c;
    dock: bottom;
}

.ok   { color: #30d158; }
.warn { color: #ff9f0a; }
.err  { color: #ff453a; }
.blue { color: #0a84ff; }
.dim  { color: #636366; }
.mid  { color: #8e8e93; }
"""


class MetricCard(Static):
    """Big-number metric card — Apple style."""

    def __init__(self, label: str, value: str = "—", color: str = "#f2f2f7", **kw):
        super().__init__(**kw)
        self._label = label
        self._value = value
        self._color = color

    def render(self) -> str:
        return f"[bold {self._color}]{self._value}[/bold {self._color}]\n[#636366]{self._label}[/#636366]"

    def update_metric(self, value: str, color: str = "#f2f2f7") -> None:
        self._value = value
        self._color = color
        self.refresh()


class PKGApp(App):
    """Personal Knowledge Graph — PKG TUI."""

    TITLE = "PKG"
    CSS = THEME

    BINDINGS = [
        Binding("ctrl+h", "show_help", "Help", show=False),
        Binding("q", "quit", "Quit", show=False),
        Binding("1", "activate_tab('dashboard')", show=False),
        Binding("2", "activate_tab('intake')", show=False),
        Binding("3", "activate_tab('search')", show=False),
        Binding("4", "activate_tab('entities')", show=False),
        Binding("5", "activate_tab('settings')", show=False),
        Binding("6", "activate_tab('graph')", show=False),
    ]

    async def on_mount(self) -> None:
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, os.getenv("LOG_LEVEL", "INFO"))
            )
        )
        has_docs = await self._has_documents()
        if not has_docs:
            from src.tui.screens.welcome import WelcomeScreen

            await self.push_screen(WelcomeScreen())

    async def _has_documents(self) -> bool:
        try:
            from src.shared.db import get_pool

            pool = await get_pool()
            async with pool.connection() as conn:
                result = await conn.execute("SELECT count(*) FROM documents")
                row = await result.fetchone()
                return row is not None and row[0] > 0
        except Exception:
            return False

    def compose(self) -> ComposeResult:
        from src.tui.screens.dashboard import DashboardView
        from src.tui.screens.entities import EntitiesView
        from src.tui.screens.graph import GraphView
        from src.tui.screens.intake import IntakeView
        from src.tui.screens.search import SearchView
        from src.tui.screens.settings import SettingsView

        yield Header(show_clock=True)
        with TabbedContent(initial="dashboard"):
            with TabPane("Dashboard", id="dashboard"):
                yield DashboardView(id="v-dashboard")
            with TabPane("Intake", id="intake"):
                yield IntakeView(id="v-intake")
            with TabPane("Search", id="search"):
                yield SearchView(id="v-search")
            with TabPane("Entities", id="entities"):
                yield EntitiesView(id="v-entities")
            with TabPane("Settings", id="settings"):
                yield SettingsView(id="v-settings")
            with TabPane("Graph", id="graph"):
                yield GraphView(id="v-graph")

    def action_show_help(self) -> None:
        from src.tui.screens.help import HelpOverlay

        self.push_screen(HelpOverlay())

    def action_activate_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """Notify the active view so it can (re)load its data."""
        tab_id = event.tab.id
        view_id = f"v-{tab_id}"
        try:
            widget = self.query_one(f"#{view_id}")
            if hasattr(widget, "on_activated"):
                self.run_worker(widget.on_activated(), exclusive=False)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        PKGApp().run()
    except Exception as e:
        crash_log = Path("/tmp/tui_crash.log")
        try:
            with crash_log.open("w") as f:
                f.write(f"PKG TUI Crashed: {type(e).__name__}: {e}\n\n")
                traceback.print_exc(file=f)
                f.write(f"\nPython: {sys.version}\nExecutable: {sys.executable}\n")
        except Exception:
            traceback.print_exc(file=sys.stderr)
        raise
