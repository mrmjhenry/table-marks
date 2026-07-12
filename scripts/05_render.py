#!/usr/bin/env python3
"""Stage 5: Embed data/graph.json into templates/viz.html → conjecture_map.html."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "data" / "graph.json"
TEMPLATE = ROOT / "templates" / "viz.html"
KATEX_CSS = ROOT / "vendor" / "katex" / "katex.inline.css"
KATEX_JS = ROOT / "vendor" / "katex" / "katex.bundle.js"
OUT = ROOT / "conjecture_map.html"

graph_text = GRAPH.read_text()
json.loads(graph_text)  # round-trip validation before embedding

html = TEMPLATE.read_text()
for ph, content in [
    ("__GRAPH_DATA__", graph_text),
    ("__KATEX_CSS__", KATEX_CSS.read_text()),
    ("__KATEX_JS__", KATEX_JS.read_text()),
]:
    assert ph in html, f"missing placeholder {ph}"
    html = html.replace(ph, content)
assert "</script>" in html and "<canvas" in html

OUT.write_text(html)
print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
