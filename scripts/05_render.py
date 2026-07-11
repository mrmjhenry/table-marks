#!/usr/bin/env python3
"""Stage 5: Embed data/graph.json into templates/viz.html → conjecture_map.html."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "data" / "graph.json"
TEMPLATE = ROOT / "templates" / "viz.html"
OUT = ROOT / "conjecture_map.html"

graph_text = GRAPH.read_text()
json.loads(graph_text)  # round-trip validation before embedding

html = TEMPLATE.read_text()
assert "__GRAPH_DATA__" in html
html = html.replace("__GRAPH_DATA__", graph_text)
assert "</script>" in html and "<canvas" in html

OUT.write_text(html)
print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
