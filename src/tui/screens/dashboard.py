"""Dashboard screen — service health, chunk counts, error log."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


class DashboardScreen(Screen):
    """Main dashboard: service health + pipeline status."""

    BINDINGS = [
        Binding("?", "app.toggle_help", "Help"),
        Binding("r", "retry_errors", "Retry errors"),
        Binding("s", "system_reset", "System reset"),
    ]

    DEFAULT_CSS = """
    DashboardScreen {
        layout: grid;
        grid-size: 2;
        grid-columns: 20 1fr;
    }
    #sidebar { height: 100%; border-right: solid $panel; padding: 1; }
    #main-panel { padding: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("PKG  ·  v0.1.0", id="sidebar")
        yield Static("Dashboard — loading…", id="main-panel")
        yield Footer()

    def action_retry_errors(self) -> None:
        self.notify("Retry triggered (Epic 1)")

    def action_system_reset(self) -> None:
        self.notify("System reset (Epic 1)")
