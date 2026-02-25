"""Settings view — search weights, PII report, bulk redact."""
from __future__ import annotations

import os

import httpx
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import DataTable, Input, Static


class SettingsView(Widget):
    """Runtime configuration and PII management."""

    DEFAULT_CSS = """
    SettingsView {
        background: #1c1c1e;
        height: 1fr;
        layout: vertical;
    }

    .settings-section {
        color: #636366;
        text-style: bold;
        height: 1;
        padding: 0 2;
        margin-top: 1;
        background: #1c1c1e;
    }

    .weight-row {
        layout: horizontal;
        height: 3;
        margin: 0 2;
    }

    .weight-label {
        color: #8e8e93;
        width: 18;
        content-align: left middle;
        padding: 0 1;
    }

    .weight-input {
        width: 12;
        background: #2c2c2e;
        border: solid #48484a;
        color: #f2f2f7;
        height: 3;
    }

    .weight-input:focus { border: solid #0a84ff; }

    #config-info {
        color: #636366;
        height: 1;
        padding: 0 2;
        margin-bottom: 1;
    }

    #pii-table {
        margin: 0 2;
        height: 1fr;
        border: solid #3a3a3c;
    }

    #settings-status {
        background: #2c2c2e;
        color: #636366;
        height: 1;
        padding: 0 2;
        border-top: solid #3a3a3c;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("s", "save_weights", "Save weights"),
        Binding("p", "load_pii", "PII report"),
        Binding("R", "bulk_redact", "Bulk redact"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("SEARCH WEIGHTS", classes="settings-section")
        with Static(classes="weight-row"):
            yield Static("BM25 weight", classes="weight-label")
            yield Input(value="0.5", id="bm25-input", classes="weight-input")
        with Static(classes="weight-row"):
            yield Static("Vector weight", classes="weight-label")
            yield Input(value="0.5", id="vector-input", classes="weight-input")
        yield Static("", id="config-info")
        yield Static("PII REPORT", classes="settings-section")
        tbl = DataTable(id="pii-table", zebra_stripes=True)
        yield tbl
        yield Static("[#636366]s=save  p=pii  R=redact[/#636366]", id="settings-status")

    def on_mount(self) -> None:
        tbl = self.query_one(DataTable)
        tbl.add_columns("TYPE", "NAME / EXCERPT", "FLAG", "DOCS")
        self.run_worker(self._load_config(), exclusive=True)

    async def on_activated(self) -> None:
        await self._load_config()

    async def _load_config(self) -> None:
        try:
            base = f"http://localhost:{os.getenv('API_PORT', '8000')}"
            headers = {}
            key = os.getenv("API_KEY_READ", "")
            if key:
                headers["X-API-Key"] = key

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{base}/config", headers=headers)
                resp.raise_for_status()
                cfg = resp.json()

            bm25 = str(cfg.get("bm25_weight", 0.5))
            vector = str(cfg.get("vector_weight", 0.5))
            rrf_k = cfg.get("rrf_k", 60)

            self.query_one("#bm25-input", Input).value = bm25
            self.query_one("#vector-input", Input).value = vector
            self.query_one("#config-info", Static).update(
                f"[#636366]rrf_k={rrf_k}  ·  chunk_size={cfg.get('chunk_size', 512)}[/#636366]"
            )
        except Exception as exc:
            self.query_one("#settings-status", Static).update(f"[#ff453a]error: {exc}[/#ff453a]")

    def action_save_weights(self) -> None:
        self.run_worker(self._save_weights(), exclusive=False)

    async def _save_weights(self) -> None:
        try:
            bm25 = float(self.query_one("#bm25-input", Input).value)
            vector = float(self.query_one("#vector-input", Input).value)
            if not (0.0 <= bm25 <= 1.0 and 0.0 <= vector <= 1.0):
                self.notify("Weights must be between 0.0 and 1.0", severity="error")
                return

            base = f"http://localhost:{os.getenv('API_PORT', '8000')}"
            headers = {}
            key = os.getenv("API_KEY_WRITE", "")
            if key:
                headers["X-API-Key"] = key

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{base}/config",
                    json={"bm25_weight": bm25, "vector_weight": vector},
                    headers=headers,
                )
                resp.raise_for_status()

            self.notify("Weights saved", severity="information")
        except Exception as exc:
            self.notify(f"Save failed: {exc}", severity="error")

    def action_load_pii(self) -> None:
        self.run_worker(self._load_pii(), exclusive=False)

    async def _load_pii(self) -> None:
        try:
            base = f"http://localhost:{os.getenv('API_PORT', '8000')}"
            headers = {}
            key = os.getenv("API_KEY_READ", "")
            if key:
                headers["X-API-Key"] = key

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{base}/pii/report", headers=headers)
                resp.raise_for_status()
                data = resp.json()

            tbl = self.query_one(DataTable)
            tbl.clear()

            for p in data.get("persons", []):
                tbl.add_row("PERSON", p.get("display_name", "?"), "[#ff9f0a]pii=true[/#ff9f0a]", str(p.get("doc_count", 0)))

            for c in data.get("pii_chunks", []):
                excerpt = (c.get("text", "")[:60]).replace("\n", " ")
                tbl.add_row("CHUNK", excerpt, "[#ff9f0a]detected[/#ff9f0a]", c.get("doc_id", "?")[:8])
        except Exception as exc:
            self.notify(f"PII report failed: {exc}", severity="error")

    def action_bulk_redact(self) -> None:
        self.run_worker(self._bulk_redact(), exclusive=False)

    async def _bulk_redact(self) -> None:
        self.query_one("#settings-status", Static).update("[#ff9f0a]redacting…[/#ff9f0a]")
        try:
            base = f"http://localhost:{os.getenv('API_PORT', '8000')}"
            headers = {}
            key = os.getenv("API_KEY_WRITE", "")
            if key:
                headers["X-API-Key"] = key

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(f"{base}/pii/bulk-redact", headers=headers)
                resp.raise_for_status()
                data = resp.json()

            count = data.get("redacted", 0)
            self.notify(f"Redacted {count} chunks", severity="information")
        except Exception as exc:
            self.notify(f"Redact failed: {exc}", severity="error")
