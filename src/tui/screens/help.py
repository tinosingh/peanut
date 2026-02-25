"""Help overlay — toggled by '?' on any screen."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Static

HELP_TEXT = """\
[bold cyan]PKG — Key Bindings[/bold cyan]

[bold]Global[/bold]
  [green]?[/green]          Toggle this help overlay
  [green]q[/green]          Quit
  [green]/[/green]          Jump to Search

[bold]Dashboard[/bold]
  [green]R[/green]          Retry dead-letter errors
  [green]S[/green]          System reset (docker compose down -v + up)

[bold]Intake[/bold]
  [green]D[/green]          Drop / remove selected file
  [green]P[/green]          Pause / resume file watcher
  [green]R[/green]          Retry errored files
  [green]S[/green]          System reset

[bold]Search[/bold]
  [green]Enter[/green]      Expand chunk inline
  [green]E[/green]          Open in Obsidian or $EDITOR
  [green]O[/green]          Open raw path in $PAGER
  [green]↑ ↓[/green]        Navigate results

[bold]Entities[/bold]
  [green]M[/green]          Merge candidates (requires confirmation)
  [green]X[/green]          Dismiss candidate
  [green]I[/green]          Inspect shared documents

[bold]Graph[/bold]
  [green]Enter[/green]      Set node as new root
  [green]Backspace[/green]  Return to previous root
  [green]X[/green]          Export subgraph as graph.html (Vis.js)
"""


class HelpOverlay(ModalScreen):
    """Full-screen help overlay. Press ? or Escape to dismiss."""

    BINDINGS = [
        Binding("?", "dismiss", "Close help"),
        Binding("escape", "dismiss", "Close help"),
    ]

    DEFAULT_CSS = """
    HelpOverlay {
        align: center middle;
    }
    HelpOverlay > #help-container {
        width: 70;
        height: auto;
        max-height: 80vh;
        background: $surface;
        border: round $primary;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Static(id="help-container"):
            yield Static(HELP_TEXT, markup=True)
            yield Button("Close  [Esc]", id="close-btn", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss()
