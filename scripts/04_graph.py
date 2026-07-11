#!/usr/bin/env python3
"""Stage 4: Build the conjecture graph from normalized objects.

Bipartite conjecture↔object incidence projected to a weighted
conjecture–conjecture graph: edge weight = Σ idf(o)² over shared objects o,
so rare shared objects dominate. Ubiquitous objects are excluded from the
projection (kept as filterable tags). Edges are pruned to keep the map
readable.

Output: data/graph.json
"""
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CONJECTURES = ROOT / "data" / "conjectures.parquet"
NORMALIZED = ROOT / "data" / "normalized.jsonl"
VOCAB = ROOT / "data" / "vocab.json"
OUT = ROOT / "data" / "graph.json"

UBIQUITY_CUTOFF = 0.15  # objects in >15% of conjectures excluded from projection
TOP_K_EDGES = 6         # keep union of each node's top-k edges
DROP_QUANTILE = 0.25    # then drop the bottom quartile by weight


def main():
    df = pd.read_parquet(CONJECTURES).set_index("content_hash")
    vocab = json.loads(VOCAB.read_text())

    objects_of = {}
    for line in NORMALIZED.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            if rec["content_hash"] in df.index:
                objects_of[rec["content_hash"]] = rec["objects"]

    n = len(objects_of)
    obj_df = Counter(o for objs in objects_of.values() for o in objs)
    ubiquitous = {o for o, c in obj_df.items() if c > UBIQUITY_CUTOFF * n}
    idf = {o: math.log(n / c) for o, c in obj_df.items()}
    print(f"{n} conjectures, {len(obj_df)} objects in use, "
          f"{len(ubiquitous)} excluded as ubiquitous: {sorted(ubiquitous)}")

    # invert: object -> conjectures
    conj_of = defaultdict(list)
    for chash, objs in objects_of.items():
        for o in objs:
            if o not in ubiquitous:
                conj_of[o].append(chash)

    # project
    weights = Counter()
    shared = defaultdict(list)
    for o, members in conj_of.items():
        if len(members) < 2 or len(members) > 200:
            continue
        w = idf[o] ** 2
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                key = tuple(sorted((members[i], members[j])))
                weights[key] += w
                shared[key].append(o)
    print(f"raw projection: {len(weights)} edges")

    # prune: union of each node's top-k edges
    by_node = defaultdict(list)
    for (a, b), w in weights.items():
        by_node[a].append((w, (a, b)))
        by_node[b].append((w, (a, b)))
    keep = set()
    for node, edges in by_node.items():
        edges.sort(reverse=True)
        keep.update(k for _, k in edges[:TOP_K_EDGES])
    kept = {k: weights[k] for k in keep}
    if kept:
        cutoff = sorted(kept.values())[int(len(kept) * DROP_QUANTILE)]
        kept = {k: w for k, w in kept.items() if w >= cutoff}
    print(f"pruned: {len(kept)} edges")

    # graph stats
    adj = defaultdict(set)
    for a, b in kept:
        adj[a].add(b)
        adj[b].add(a)
    seen, components = set(), []
    for start in objects_of:
        if start in seen or start not in adj:
            continue
        comp, stack = 0, [start]
        seen.add(start)
        while stack:
            u = stack.pop()
            comp += 1
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        components.append(comp)
    components.sort(reverse=True)
    isolated = sum(1 for c in objects_of if c not in adj)
    max_deg = max((len(v) for v in adj.values()), default=0)
    print(f"components: {components[:5]}… giant={components[0] if components else 0}/{n} "
          f"({100 * (components[0] if components else 0) / n:.0f}%), "
          f"isolated: {isolated} ({100 * isolated / n:.0f}%), max degree: {max_deg}")

    # node payloads
    nodes = []
    for chash, objs in objects_of.items():
        r = df.loc[chash]
        nodes.append({
            "id": chash,
            "title": r["title"],
            "cat": r["primary_category"] or "",
            "label": r["latest_label"],
            "interest": round(float(r["latest_interestingness_score"]), 3),
            "viability": round(float(r["latest_viability_score"]), 3),
            "url": r["abs_url"],
            "authors": list(r["authors"])[:6],
            "objects": objs,
            "text": r["display_text"],
        })
    edges = [
        {"s": a, "t": b, "w": round(w, 3),
         "shared": sorted(shared[(a, b)], key=lambda o: -idf[o])[:6]}
        for (a, b), w in kept.items()
    ]
    obj_table = [
        {"name": o, "df": obj_df[o], "area": vocab.get(o, {}).get("area", "other"),
         "ubiquitous": o in ubiquitous}
        for o in sorted(obj_df, key=lambda o: -obj_df[o])
    ]

    graph = {"nodes": nodes, "edges": edges, "objects": obj_table}
    OUT.write_text(json.dumps(graph))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB): "
          f"{len(nodes)} nodes, {len(edges)} edges, {len(obj_table)} objects")

    top = sorted(((sum(idf[o] ** 2 for _ in conj_of[o]) * 0, obj_df[o], o) for o in conj_of), reverse=True)[:20]
    print("\ntop objects by df (in projection):")
    for _, c, o in top:
        print(f"  {c:4d}  {o}")


if __name__ == "__main__":
    main()
