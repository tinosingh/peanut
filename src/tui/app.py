"""PKG Textual application — main app class."""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding

from src.tui.screens.dashboard import DashboardScreen
from src.tui.screens.help import HelpOverlay
from src.tui.screens.welcome import WelcomeScreen


class PKGApp(App):
    """Personal Knowledge Graph TUI.

    Screens: Dashboard, Intake, Search, Entities, Graph, Settings
    Global bindings: ?, q, /
    Footer bar auto-renders binding descriptions.
    """

    TITLE = "PKG"
    SUB_TITLE = "Personal Knowledge Graph"

    BINDINGS = [
        Binding("?",     "toggle_help",    "Help"),
        Binding("q",     "quit",           "Quit"),
        Binding("/",     "focus_search",   "Search"),
        Binding("ctrl+d","switch_dashboard","Dashboard"),
    ]

    CSS = """
    PKGApp {
        background: $background;
    }
    """

    async def on_mount(self) -> None:
        """Push the appropriate initial screen."""
        has_docs = await self._has_documents()
        if has_docs:
            await self.push_screen(DashboardScreen())
        else:
            await self.push_screen(WelcomeScreen())

    async def _has_documents(self) -> bool:
        """Return True if at least one document has been ingested."""
        try:
            from src.shared.db import get_pool
            pool = await get_pool()
            async with pool.connection() as conn:
                row = await conn.fetchrow("SELECT count(*) FROM documents")
                return row is not None and row[0] > 0
        except Exception:
            return False

    def action_toggle_help(self) -> None:
        """Toggle the full-screen help overlay."""
        self.push_screen(HelpOverlay())

    def action_focus_search(self) -> None:
        """Switch to Search screen."""
        self.notify("Search screen (Epic 2)")

    def action_switch_dashboard(self) -> None:
        """Switch to Dashboard screen."""
        self.switch_screen(DashboardScreen())
