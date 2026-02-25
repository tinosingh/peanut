"""Vis.js graph export — render_visjs() produces a self-contained HTML file.

The HTML embeds the Vis.js network layout via CDN (no local assets needed).
Nodes are coloured by label: Person=blue, Document=green, Concept=orange.
"""
from __future__ import annotations

import json

_VIS_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>PKG Subgraph</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  body {{ margin: 0; background: #1a1a2e; }}
  #graph {{ width: 100vw; height: 100vh; }}
</style>
</head>
<body>
<div id="graph"></div>
<script>
  const nodes = new vis.DataSet({nodes_json});
  const edges = new vis.DataSet({edges_json});
  const container = document.getElementById("graph");
  const data = {{ nodes, edges }};
  const options = {{
    nodes: {{ font: {{ color: "#e0e0e0" }}, borderWidth: 2 }},
    edges: {{ color: "#666", arrows: "to", font: {{ color: "#aaa", size: 11 }} }},
    physics: {{ stabilization: {{ iterations: 100 }} }},
    layout: {{ improvedLayout: true }},
    background: {{ color: "#1a1a2e" }}
  }};
  new vis.Network(container, data, options);
</script>
</body>
</html>
"""

_LABEL_COLORS = {
    "Person": {"background": "#2d6a9f", "border": "#5ba3dc"},
    "Document": {"background": "#2d7a3a", "border": "#5dc46a"},
    "Concept": {"background": "#8b5e00", "border": "#d4920a"},
}
_DEFAULT_COLOR = {"background": "#555", "border": "#999"}


def render_visjs(
    nodes: list[dict],
    edges: list[dict],
) -> str:
    """Render a subgraph as a self-contained Vis.js HTML string.

    Args:
        nodes: List of dicts with keys: id, label, title (tooltip), group
        edges: List of dicts with keys: from, to, label

    Returns:
        Complete HTML string for the graph visualisation.
    """
    vis_nodes = []
    for n in nodes:
        group = n.get("group", "")
        color = _LABEL_COLORS.get(group, _DEFAULT_COLOR)
        vis_nodes.append({
            "id": n["id"],
            "label": n.get("label", n["id"]),
            "title": n.get("title", ""),
            "color": color,
            "group": group,
        })

    vis_edges = []
    for i, e in enumerate(edges):
        vis_edges.append({
            "id": i,
            "from": e["from"],
            "to": e["to"],
            "label": e.get("label", ""),
        })

    return _VIS_HTML_TEMPLATE.format(
        nodes_json=json.dumps(vis_nodes),
        edges_json=json.dumps(vis_edges),
    )
