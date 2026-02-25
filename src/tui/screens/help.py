"""Help overlay — all key bindings."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class HelpOverlay(ModalScreen):
    """Keyboard shortcuts help modal."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=False),
        Binding("ctrl+h", "dismiss", "Close", show=False),
    ]

    DEFAULT_CSS = """
    HelpOverlay {
        align: center middle;
        background: rgba(0,0,0,0.7);
    }

    #help-box {
        background: #2c2c2e;
        border: solid #3a3a3c;
        padding: 2 4;
        width: 64;
        height: auto;
        max-height: 80vh;
    }

    #help-title {
        color: #f2f2f7;
        text-style: bold;
        content-align: center middle;
        text-align: center;
        height: 1;
        margin-bottom: 1;
    }

    .help-section {
        color: #636366;
        text-style: bold;
        height: 1;
        margin-top: 1;
    }

    .help-row {
        color: #8e8e93;
        height: 1;
        padding: 0 1;
    }

    #close-btn {
        margin-top: 1;
        background: #3a3a3c;
        border: solid #48484a;
        color: #8e8e93;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        with Static(id="help-box"):
            yield Static("PKG — Key Bindings", id="help-title")

            yield Static("GLOBAL", classes="help-section")
            yield Static(
                "[#0a84ff]1–6[/#0a84ff]  switch tabs  ·  [#0a84ff]ctrl+h[/#0a84ff]  help  ·  [#0a84ff]q[/#0a84ff]  quit",
                classes="help-row",
            )

            yield Static("DASHBOARD", classes="help-section")
            yield Static("[#0a84ff]r[/#0a84ff]  refresh", classes="help-row")

            yield Static("INTAKE", classes="help-section")
            yield Static(
                "[#0a84ff]p[/#0a84ff]  pause  ·  [#0a84ff]r[/#0a84ff]  retry",
                classes="help-row",
            )

            yield Static("SEARCH", classes="help-section")
            yield Static(
                "[#0a84ff]↵[/#0a84ff]  search  ·  [#0a84ff]enter[/#0a84ff]  expand",
                classes="help-row",
            )

            yield Static("ENTITIES", classes="help-section")
            yield Static(
                "[#0a84ff]m[/#0a84ff]  merge (2×)  ·  [#0a84ff]r[/#0a84ff]  reload",
                classes="help-row",
            )

            yield Static("SETTINGS", classes="help-section")
            yield Static(
                "[#0a84ff]s[/#0a84ff]  save  ·  [#0a84ff]p[/#0a84ff]  PII  ·  [#0a84ff]R[/#0a84ff]  redact",
                classes="help-row",
            )

            yield Static("GRAPH", classes="help-section")
            yield Static(
                "[#0a84ff]enter[/#0a84ff]  drill  ·  [#0a84ff]backspace[/#0a84ff]  back  ·  [#0a84ff]r[/#0a84ff]  reload",
                classes="help-row",
            )

            yield Button("Close  [esc]", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()
