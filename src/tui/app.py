"""PKG Textual application — main app class."""
from __future__ import annotations

from textual.app import App
from textual.binding import Binding

from src.tui.screens.dashboard import DashboardScreen
from src.tui.screens.help import HelpOverlay
from src.tui.screens.welcome import WelcomeScreen


class PKGApp(App):
    """Personal Knowledge Graph TUI.

    Screens: Dashboard, Intake, Search, Entities, Settings, Graph
    Global bindings: ?, q, /, i, e, s, g, ctrl+d
    Footer bar auto-renders binding descriptions.
    """

    TITLE = "PKG"
    SUB_TITLE = "Personal Knowledge Graph"

    BINDINGS = [
        Binding("?",      "toggle_help",       "Help"),
        Binding("q",      "quit",              "Quit"),
        Binding("/",      "goto_search",       "Search"),
        Binding("i",      "goto_intake",       "Intake"),
        Binding("e",      "goto_entities",     "Entities"),
        Binding("s",      "goto_settings",     "Settings"),
        Binding("g",      "goto_graph",        "Graph"),
        Binding("ctrl+d", "goto_dashboard",    "Dashboard"),
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
                result = await conn.execute("SELECT count(*) FROM documents")
                row = await result.fetchone()
                return row is not None and row[0] > 0
        except Exception:
            return False

    def action_toggle_help(self) -> None:
        self.push_screen(HelpOverlay())

    def action_goto_search(self) -> None:
        from src.tui.screens.search import SearchScreen
        self.push_screen(SearchScreen())

    def action_goto_intake(self) -> None:
        from src.tui.screens.intake import IntakeScreen
        self.push_screen(IntakeScreen())

    def action_goto_entities(self) -> None:
        from src.tui.screens.entities import EntitiesScreen
        self.push_screen(EntitiesScreen())

    def action_goto_settings(self) -> None:
        from src.tui.screens.settings import SettingsScreen
        self.push_screen(SettingsScreen())

    def action_goto_graph(self) -> None:
        from src.tui.screens.graph import GraphScreen
        self.push_screen(GraphScreen())

    def action_goto_dashboard(self) -> None:
        self.switch_screen(DashboardScreen())


if __name__ == "__main__":
    import sys
    import traceback
    from pathlib import Path

    try:
        PKGApp().run()
    except Exception as e:
        # Log crash to file since Textual captures stdout/stderr
        crash_log = Path("/tmp/tui_crash.log")
        try:
            with crash_log.open("w") as f:
                f.write(f"PKG TUI Crashed: {type(e).__name__}: {e}\n\n")
                f.write("=" * 60 + "\n")
                f.write("Full Traceback:\n")
                f.write("=" * 60 + "\n")
                traceback.print_exc(file=f)
                f.write("\n" + "=" * 60 + "\n")
                f.write(f"Python: {sys.version}\n")
                f.write(f"Executable: {sys.executable}\n")
        except Exception as log_err:
            # If even logging fails, print to stderr
            print(f"FATAL: Crash logging failed: {log_err}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
        # Re-raise so Docker sees the failure
        raise
