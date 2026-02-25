"""Knowledge graph screen — Textual Tree widget over FalkorDB subgraph.

Navigate the graph with:
  Enter     — drill into selected node (set as new root)
  Backspace — return to previous root
  R         — reload from FalkorDB
  X         — export current subgraph as graph.html (Vis.js) and open in browser
"""
from __future__ import annotations

import webbrowser
from pathlib import Path

import structlog
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Static, Tree
from textual.widgets.tree import TreeNode

log = structlog.get_logger()

_EXPORT_PATH = Path("./data/graph.html")


class GraphScreen(Screen):
    """Cypher-driven subgraph rendered as a navigable Textual Tree."""

    BINDINGS = [
        Binding("r",         "reload",        "Reload"),
        Binding("x",         "export_graph",  "Export HTML"),
        Binding("backspace", "go_back",        "Back"),
        Binding("?",         "app.toggle_help", "Help"),
        Binding("q",         "app.quit",        "Quit"),
    ]

    DEFAULT_CSS = """
    GraphScreen {
        layout: vertical;
    }
    GraphScreen > #graph-tree {
        border: round $accent;
        height: 1fr;
        padding: 1;
    }
    GraphScreen > #status-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(self, root_email: str | None = None) -> None:
        super().__init__()
        self._root_email = root_email
        self._history: list[str] = []
        self._current_nodes: list[dict] = []
        self._current_edges: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Tree("Knowledge Graph", id="graph-tree")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._load_graph, exclusive=True)

    async def _load_graph(self) -> None:
        tree = self.query_one(Tree)
        tree.clear()
        status = self.query_one("#status-bar", Static)
        status.update("Loading graph…")

        root_email = self._root_email
        nodes, edges = await _fetch_subgraph(root_email)
        self._current_nodes = nodes
        self._current_edges = edges

        if not nodes:
            tree.root.set_label("No graph data — ingest some documents first")
            status.update("Graph empty")
            return

        # Build adjacency map
        adj: dict[str, list[tuple[str, str, str]]] = {}  # id -> [(edge_label, target_id, target_label)]
        for e in edges:
            adj.setdefault(e["from"], []).append((e.get("label", ""), e["to"], ""))

        # Find label map
        id_to_node = {n["id"]: n for n in nodes}

        # Render root nodes (Persons with no incoming edges or the root_email node)
        root_ids = [
            n["id"] for n in nodes
            if n.get("group") == "Person"
            and (root_email is None or n.get("label", "") == root_email)
        ]
        if not root_ids:
            root_ids = [nodes[0]["id"]]

        tree.root.set_label("Subgraph")
        tree.root.expand()

        for rid in root_ids[:10]:  # cap at 10 roots for readability
            n = id_to_node.get(rid, {})
            root_node = tree.root.add(
                f"[bold cyan]({n.get('group', '')})[/bold cyan] {n.get('label', rid)}",
                data=rid,
            )
            _populate_tree(root_node, rid, adj, id_to_node, depth=0, max_depth=3, visited=set())
            root_node.expand()

        status.update(f"{len(nodes)} nodes · {len(edges)} edges · root: {root_email or 'all'}")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Enter on a node drills into it as the new root."""
        node_id = event.node.data
        if node_id:
            if self._root_email:
                self._history.append(self._root_email)
            self._root_email = node_id
            self.run_worker(self._load_graph, exclusive=True)

    def action_go_back(self) -> None:
        if self._history:
            self._root_email = self._history.pop()
            self.run_worker(self._load_graph, exclusive=True)

    def action_reload(self) -> None:
        self.run_worker(self._load_graph, exclusive=True)

    def action_export_graph(self) -> None:
        self.run_worker(self._do_export, thread=True)

    def _do_export(self) -> None:
        from src.tui.screens.graph_export import render_visjs

        if not self._current_nodes:
            self.call_from_thread(
                self.notify, "No graph data to export", severity="warning"
            )
            return

        html = render_visjs(self._current_nodes, self._current_edges)
        _EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _EXPORT_PATH.write_text(html, encoding="utf-8")
        webbrowser.open(f"file://{_EXPORT_PATH.resolve()}")
        self.call_from_thread(
            self.notify, f"Graph exported to {_EXPORT_PATH}", severity="information"
        )


def _populate_tree(
    node: TreeNode,
    node_id: str,
    adj: dict,
    id_to_node: dict,
    depth: int,
    max_depth: int,
    visited: set,
) -> None:
    """Recursively add children to a tree node up to max_depth."""
    if depth >= max_depth or node_id in visited:
        return
    visited = visited | {node_id}
    for edge_label, child_id, _ in adj.get(node_id, []):
        child = id_to_node.get(child_id, {})
        group = child.get("group", "")
        label = child.get("label", child_id)
        color = {"Person": "cyan", "Document": "green", "Concept": "yellow"}.get(group, "white")
        child_node = node.add(
            f"[{color}][:{edge_label}][/{color}] → [{color}]({group})[/{color}] {label}",
            data=child_id,
        )
        _populate_tree(child_node, child_id, adj, id_to_node, depth + 1, max_depth, visited)


async def _fetch_subgraph(
    root_email: str | None,
    limit: int = 100,
) -> tuple[list[dict], list[dict]]:
    """Fetch a subgraph from FalkorDB centred on root_email.

    Falls back to an empty result if FalkorDB is unavailable.
    """
    import os

    try:
        from falkordb import FalkorDB

        host = os.getenv("FALKORDB_HOST", "localhost")
        port = int(os.getenv("FALKORDB_PORT", "6379"))
        db = FalkorDB(host=host, port=port)
        graph = db.select_graph("pkg")

        if root_email:
            query = """
            MATCH (p:Person {email: $email})-[r]->(n)
            RETURN p.email AS from_id, 'Person' AS from_group, p.email AS from_label,
                   type(r) AS edge_label,
                   n.id AS to_id,
                   labels(n)[0] AS to_group,
                   coalesce(n.name, n.title, n.email, n.id) AS to_label
            LIMIT $limit
            """
            result = graph.query(query, {"email": root_email, "limit": limit})
        else:
            query = """
            MATCH (a)-[r]->(b)
            RETURN a.id AS from_id,
                   labels(a)[0] AS from_group,
                   coalesce(a.name, a.title, a.email, a.id) AS from_label,
                   type(r) AS edge_label,
                   b.id AS to_id,
                   labels(b)[0] AS to_group,
                   coalesce(b.name, b.title, b.email, b.id) AS to_label
            LIMIT $limit
            """
            result = graph.query(query, {"limit": limit})

        nodes: dict[str, dict] = {}
        edges: list[dict] = []

        for row in result.result_set:
            from_id, from_group, from_label, edge_label, to_id, to_group, to_label = row
            if from_id and from_id not in nodes:
                nodes[from_id] = {"id": from_id, "group": from_group or "", "label": from_label or from_id}
            if to_id and to_id not in nodes:
                nodes[to_id] = {"id": to_id, "group": to_group or "", "label": to_label or to_id}
            if from_id and to_id:
                edges.append({"from": from_id, "to": to_id, "label": edge_label or ""})

        return list(nodes.values()), edges

    except Exception as exc:
        log.warning("graph_fetch_failed", error=str(exc))
        return [], []
