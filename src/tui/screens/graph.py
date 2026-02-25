"""Graph view — FalkorDB knowledge graph navigation."""

from __future__ import annotations

import os
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static, Tree

_COLOR = {"Person": "#64d2ff", "Document": "#30d158", "Concept": "#ff9f0a"}


class GraphView(Widget):
    """FalkorDB graph tree with drill-down navigation."""

    DEFAULT_CSS = """
    GraphView {
        background: #1c1c1e;
        height: 1fr;
        layout: vertical;
    }

    #graph-header {
        background: #2c2c2e;
        color: #8e8e93;
        height: 1;
        padding: 0 2;
        border-bottom: solid #3a3a3c;
    }

    #graph-tree {
        height: 1fr;
        margin: 1 2;
        border: solid #3a3a3c;
        background: #1c1c1e;
    }

    #graph-status {
        background: #2c2c2e;
        color: #636366;
        height: 1;
        padding: 0 2;
        border-top: solid #3a3a3c;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("r", "reload", "Reload"),
        Binding("backspace", "go_back", "Back"),
        Binding("enter", "drill_in", "Drill in"),
    ]

    _history: list[str] = []
    _root_email: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("[#8e8e93]Knowledge Graph[/#8e8e93]", id="graph-header")
        tree: Tree[str] = Tree("PKG", id="graph-tree")
        tree.root.expand()
        yield tree
        yield Static("[#636666]loading…[/#636666]", id="graph-status")

    def on_mount(self) -> None:
        self.run_worker(self._load(None), exclusive=True)

    async def on_activated(self) -> None:
        await self._load(self._root_email)

    def action_reload(self) -> None:
        self._history.clear()
        self._root_email = None
        self.run_worker(self._load(None), exclusive=True)

    def action_go_back(self) -> None:
        if self._history:
            self._root_email = self._history.pop()
            self.run_worker(self._load(self._root_email), exclusive=True)

    def action_drill_in(self) -> None:
        tree = self.query_one(Tree)
        node = tree.cursor_node
        if node and node.data:
            if self._root_email:
                self._history.append(self._root_email)
            self._root_email = node.data
            self.run_worker(self._load(node.data), exclusive=True)

    async def _load(self, root_email: str | None) -> None:
        try:
            import falkordb

            host = os.getenv("FALKORDB_HOST", "pkg-graph")
            port = int(os.getenv("FALKORDB_PORT", "6379"))
            client = falkordb.FalkorDB(host=host, port=port)
            g = client.select_graph("pkg")

            if root_email:
                result = g.query(
                    "MATCH (p:Person {email: $email})-[r]->(n) "
                    "RETURN p.email, labels(p)[0], coalesce(p.name, p.email, p.id), "
                    "type(r), n.id, labels(n)[0], coalesce(n.name, n.title, n.email, n.id) LIMIT 50",
                    {"email": root_email},
                )
            else:
                result = g.query(
                    "MATCH (a)-[r]->(b) "
                    "RETURN a.id, labels(a)[0], coalesce(a.name, a.title, a.email, a.id), "
                    "type(r), b.id, labels(b)[0], coalesce(b.name, b.title, b.email, b.id) LIMIT 100"
                )

            rows = list(result.result_set)
            tree = self.query_one(Tree)
            tree.clear()
            root_label = root_email or "Knowledge Graph"
            root_node = tree.root
            root_node.set_label(f"[bold #f2f2f7]{root_label}[/bold #f2f2f7]")
            root_node.expand()

            seen: dict[str, Any] = {}
            for row in rows:
                from_id, from_group, from_label, edge, to_id, to_group, to_label = row
                fc = _COLOR.get(from_group or "", "#8e8e93")
                tc = _COLOR.get(to_group or "", "#8e8e93")

                parent = seen.get(str(from_id))
                if parent is None:
                    parent = root_node.add(
                        f"[{fc}]{from_label or from_id}[/{fc}]", data=str(from_id)
                    )
                    seen[str(from_id)] = parent

                parent.add(
                    f"[{tc}]{to_label or to_id}[/{tc}]  [#3a3a3c]{edge}[/#3a3a3c]",
                    data=str(to_id),
                )

            self.query_one("#graph-status", Static).update(
                f"[#636366]{len(rows)} edges  ·  enter=drill  backspace=back[/#636366]"
            )

        except Exception as exc:
            self.query_one("#graph-status", Static).update(f"[#ff453a]{exc}[/#ff453a]")
