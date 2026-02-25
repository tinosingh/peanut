"""First-run welcome screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Static


class WelcomeScreen(Screen):
    """Shown when no documents exist."""

    BINDINGS = [
        Binding("q", "app.quit", "Quit"),
        Binding("ctrl+h", "app.show_help", "Help", show=False),
    ]

    DEFAULT_CSS = """
    WelcomeScreen {
        background: #1c1c1e;
        align: center middle;
    }

    #welcome-box {
        background: #2c2c2e;
        border: solid #3a3a3c;
        padding: 3 6;
        width: 58;
        height: auto;
        content-align: center middle;
    }

    #logo {
        color: #f2f2f7;
        text-style: bold;
        content-align: center middle;
        height: 3;
        text-align: center;
    }

    #tagline {
        color: #636366;
        content-align: center middle;
        text-align: center;
        height: 1;
    }

    #divider-line {
        background: #3a3a3c;
        height: 1;
        margin: 1 0;
    }

    #instructions {
        color: #8e8e93;
        padding: 1 0;
    }

    #hint {
        color: #48484a;
        content-align: center middle;
        text-align: center;
        height: 1;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Static(id="welcome-box"):
            yield Static("[bold #f2f2f7]PKG[/bold #f2f2f7]", id="logo")
            yield Static("[#636366]Personal Knowledge Graph[/#636366]", id="tagline")
            yield Static("", id="divider-line")
            yield Static(
                "  1  Copy files ([#30d158].mbox .pdf .md[/#30d158]) into drop-zone/\n"
                "  2  Ingest worker detects them automatically\n"
                "  3  Screen dismisses after first document indexed",
                id="instructions",
            )
            yield Static("[#48484a]watching for files…[/#48484a]", id="hint")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(5.0, self._poll)

    async def _poll(self) -> None:
        try:
            from src.shared.db import get_pool

            pool = await get_pool()
            async with pool.connection() as conn:
                result = await conn.execute("SELECT count(*) FROM documents")
                row = await result.fetchone()
                if row and row[0] > 0:
                    self.app.pop_screen()
        except Exception:
            pass
