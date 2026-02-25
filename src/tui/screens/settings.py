"""Settings screen — BM25/vector weight sliders + PII report.

T-043: PII Report section lists persons(pii=true) + chunks(pii_detected=true)
T-044: Weight sliders write bm25_weight/vector_weight to config table
"""
from __future__ import annotations

import os

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Static


class SettingsScreen(Screen):
    """Operator settings: search weights, PII report, bulk redact.

    Key bindings:
      S  — save weight changes
      P  — view PII report
      R  — bulk redact selected PII chunks
    """

    BINDINGS = [
        Binding("?",      "app.toggle_help", "Help"),
        Binding("escape", "app.pop_screen",  "Back"),
        Binding("s",      "save_weights",    "Save weights"),
        Binding("p",      "show_pii_report", "PII report"),
        Binding("r",      "bulk_redact",     "Bulk redact"),
    ]

    DEFAULT_CSS = """
    SettingsScreen { layout: vertical; }
    #weight-panel { height: 6; border: solid $primary; padding: 1; }
    #pii-table { height: 1fr; }
    #status { height: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(
            "BM25 weight (0.0–1.0):  [enter value]   Vector weight (0.0–1.0):  [enter value]\n"
            "rrf_k: (read-only from config)",
            id="weight-panel",
        )
        yield Input(placeholder="bm25_weight (0.0–1.0)", id="bm25-input")
        yield Input(placeholder="vector_weight (0.0–1.0)", id="vec-input")
        yield DataTable(id="pii-table", zebra_stripes=True)
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("TYPE", "ID", "NAME/CHUNK", "PII FLAG", "DOC COUNT")
        self.run_worker(self._load_config(), thread=False)

    async def _load_config(self) -> None:
        import httpx
        api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{api_url}/config")
                resp.raise_for_status()
                cfg = resp.json()
            self.query_one("#bm25-input", Input).value = str(cfg.get("bm25_weight", 0.5))
            self.query_one("#vec-input",  Input).value = str(cfg.get("vector_weight", 0.5))
            rrf_k = cfg.get("rrf_k", 60)
            self.query_one("#weight-panel", Static).update(
                f"BM25 weight: {cfg.get('bm25_weight', 0.5)}   Vector weight: {cfg.get('vector_weight', 0.5)}\n"
                f"rrf_k: {rrf_k} (read-only)"
            )
        except Exception as exc:
            self.notify(f"Config load error: {exc}", severity="warning")

    async def action_save_weights(self) -> None:
        import httpx
        api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        try:
            bm25 = float(self.query_one("#bm25-input", Input).value)
            vec = float(self.query_one("#vec-input",  Input).value)
        except ValueError:
            self.notify("Invalid weight values — enter floats between 0.0 and 1.0", severity="error")
            return
        if not (0.0 <= bm25 <= 1.0 and 0.0 <= vec <= 1.0):
            self.notify("Weights must be between 0.0 and 1.0", severity="error")
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{api_url}/config",
                    json={"bm25_weight": bm25, "vector_weight": vec},
                )
                resp.raise_for_status()
            self.notify(f"Saved: bm25_weight={bm25}, vector_weight={vec}", severity="information")
        except Exception as exc:
            self.notify(f"Save failed: {exc}", severity="error")

    async def action_show_pii_report(self) -> None:
        import httpx
        api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        table = self.query_one(DataTable)
        table.clear()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{api_url}/pii/report")
                resp.raise_for_status()
                data = resp.json()
            for person in data.get("persons", []):
                table.add_row(
                    "PERSON", person["id"], person.get("display_name", ""),
                    "PII=true", str(person.get("doc_count", 0)),
                )
            for chunk in data.get("pii_chunks", []):
                table.add_row(
                    "CHUNK", chunk["id"], chunk.get("text", "")[:60],
                    "pii_detected", chunk.get("doc_id", ""),
                )
        except Exception as exc:
            self.notify(f"PII report error: {exc}", severity="error")

    async def action_bulk_redact(self) -> None:
        import httpx
        api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        status = self.query_one("#status", Static)
        status.update("Redacting PII chunks…")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f"{api_url}/pii/bulk-redact")
                resp.raise_for_status()
                data = resp.json()
            self.notify(f"Redacted {data.get('redacted', 0)} chunks", severity="information")
            status.update("")
        except Exception as exc:
            self.notify(f"Bulk redact failed: {exc}", severity="error")
            status.update("")
