"""First-run welcome screen — shown when documents table is empty."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static, Footer


WELCOME_TEXT = """\
[bold cyan]Welcome to PKG[/bold cyan]

No documents indexed yet.

[bold]Getting started:[/bold]
  1. Copy your files ([green].mbox[/green], [green].pdf[/green], [green].md[/green])
     into the [bold]drop-zone/[/bold] folder.
  2. The ingest worker will detect them automatically.
  3. This screen dismisses after the first successful ingest.

[dim]Press [bold]?[/bold] for full key-binding help.[/dim]
"""


class WelcomeScreen(Screen):
    """Shown on TUI launch when documents table is empty.
    Dismissed automatically after first successful ingest (polled every 5s).
    """

    BINDINGS = [
        Binding("?", "app.toggle_help", "Help"),
        Binding("q", "app.quit", "Quit"),
    ]

    DEFAULT_CSS = """
    WelcomeScreen {
        align: center middle;
        background: $background;
    }
    WelcomeScreen > #welcome-box {
        width: 60;
        height: auto;
        background: $surface;
        border: round $accent;
        padding: 2 4;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(WELCOME_TEXT, id="welcome-box", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        """Poll every 5s — dismiss once a document exists."""
        self.set_interval(5.0, self._check_for_documents)

    async def _check_for_documents(self) -> None:
        """Check if any documents have been ingested; if so, dismiss."""
        try:
            from src.shared.db import get_pool
            pool = await get_pool()
            async with pool.connection() as conn:
                result = await conn.execute("SELECT count(*) FROM documents")
                row = await result.fetchone()
                if row and row[0] > 0:
                    self.app.pop_screen()
        except Exception:
            pass  # DB not ready yet — keep waiting
