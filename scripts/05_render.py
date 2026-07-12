#!/usr/bin/env python3
"""Stage 5: Embed graph JSON into templates/viz.html.

Renders conjecture_map.html (publish-safe) and, when data/graph_local.json
exists, conjecture_map_local.html (full recovered text — gitignored, local
research use only).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates" / "viz.html"
KATEX_CSS = ROOT / "vendor" / "katex" / "katex.inline.css"
KATEX_JS = ROOT / "vendor" / "katex" / "katex.bundle.js"

BUILDS = [
    (ROOT / "data" / "graph.json", ROOT / "conjecture_map.html"),
    (ROOT / "data" / "graph_local.json", ROOT / "conjecture_map_local.html"),
]

template = TEMPLATE.read_text()
for graph_path, out_path in BUILDS:
    if not graph_path.exists():
        continue
    graph_text = graph_path.read_text()
    json.loads(graph_text)  # round-trip validation before embedding
    html = template
    for ph, content in [
        ("__GRAPH_DATA__", graph_text),
        ("__KATEX_CSS__", KATEX_CSS.read_text()),
        ("__KATEX_JS__", KATEX_JS.read_text()),
    ]:
        assert ph in html, f"missing placeholder {ph}"
        html = html.replace(ph, content)
    assert "</script>" in html and "<canvas" in html
    out_path.write_text(html)
    print(f"wrote {out_path.name} ({out_path.stat().st_size / 1e6:.1f} MB)")
