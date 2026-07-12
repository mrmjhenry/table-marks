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
OUT = ROOT / "data" / "graph.json"          # publish-safe (recovered text redacted)
OUT_LOCAL = ROOT / "data" / "graph_local.json"  # full text, local use only

# optional annotation stages — merged into nodes when present
MSC_ASSIGN = ROOT / "data" / "msc.jsonl"
CLUSTERS = ROOT / "data" / "clusters.jsonl"
RELATIONS = ROOT / "data" / "relations.jsonl"
LEAN = ROOT / "data" / "lean.jsonl"

WITHHELD_NOTE = ("[Statement text recovered from the arXiv source for local analysis; "
                 "omitted from the published map for licensing reasons — "
                 "follow the arXiv link to read it.]")

UBIQUITY_CUTOFF = 0.15  # objects in >15% of conjectures excluded from projection
TOP_K_EDGES = 6         # keep union of each node's top-k edges
DROP_QUANTILE = 0.25    # then drop the bottom quartile by weight

# Sharing a structure is strong evidence of working with the same objects;
# sharing a property ("isomorphism") is weak. Typed in 03b_type.py.
TYPE_WEIGHTS = {"structure": 1.0, "statement": 1.5, "invariant": 0.8,
                "property": 0.4, "discarded": 0.0}


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
    type_of = {o: vocab.get(o, {}).get("type", "structure") for o in obj_df}
    discarded = {o for o, t in type_of.items() if t == "discarded"}
    print(f"{n} conjectures, {len(obj_df)} objects in use, "
          f"{len(ubiquitous)} excluded as ubiquitous: {sorted(ubiquitous)}; "
          f"{len(discarded)} typed 'discarded' excluded")

    # invert: object -> conjectures
    conj_of = defaultdict(list)
    for chash, objs in objects_of.items():
        for o in objs:
            if o not in ubiquitous and o not in discarded:
                conj_of[o].append(chash)

    # project
    weights = Counter()
    shared = defaultdict(list)
    weight_by_type = Counter()
    for o, members in conj_of.items():
        if len(members) < 2 or len(members) > 200:
            continue
        w = idf[o] ** 2 * TYPE_WEIGHTS[type_of[o]]
        if w <= 0:
            continue
        weight_by_type[type_of[o]] += w * len(members) * (len(members) - 1) / 2
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                key = tuple(sorted((members[i], members[j])))
                weights[key] += w
                shared[key].append(o)
    print(f"raw projection: {len(weights)} edges")
    tot_w = sum(weight_by_type.values()) or 1
    print("edge weight composition by entity type: " +
          ", ".join(f"{t}: {100 * w / tot_w:.0f}%" for t, w in weight_by_type.most_common()))

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

    # optional annotations
    def load_jsonl(path):
        if not path.exists():
            return {}
        return {r["content_hash"]: r for r in
                (json.loads(l) for l in path.read_text().splitlines() if l.strip())}
    msc = load_jsonl(MSC_ASSIGN)
    clusters = load_jsonl(CLUSTERS)
    lean = load_jsonl(LEAN)
    relations = []
    if RELATIONS.exists():
        relations = [r for r in (json.loads(l) for l in RELATIONS.read_text().splitlines() if l.strip())
                     if r.get("relation") not in (None, "none")
                     and r["a"] in objects_of and r["b"] in objects_of]
    print(f"annotations: msc={len(msc)}, clusters={len(clusters)}, "
          f"lean={sum(1 for v in lean.values() if v.get('status') != 'none')}, "
          f"relations={len(relations)}")

    # node payloads
    nodes = []
    for chash, objs in objects_of.items():
        r = df.loc[chash]
        node = {
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
            "tex": r.get("render_tex", "") or "",
            "src": r.get("text_source", "dataset"),
        }
        if chash in msc and msc[chash]["codes"]:
            node["msc"] = msc[chash]["codes"]
            node["mscNames"] = msc[chash]["names"]
        if chash in clusters and clusters[chash]["cluster_id"] >= 0:
            node["cluster"] = clusters[chash]["cluster_name"]
        if chash in lean and lean[chash].get("status") != "none":
            node["lean"] = {"status": lean[chash]["status"], "decl": lean[chash]["decl"],
                            "module": lean[chash]["module"]}
        nodes.append(node)
    edges = [
        {"s": a, "t": b, "w": round(w, 3),
         "shared": sorted(shared[(a, b)], key=lambda o: -idf[o])[:6]}
        for (a, b), w in kept.items()
    ]
    rel_edges = [{"a": r["a"], "b": r["b"], "rel": r["relation"],
                  "subject": r.get("subject"), "why": r.get("justification", "")[:300]}
                 for r in relations]
    obj_table = [
        {"name": o, "df": obj_df[o], "area": vocab.get(o, {}).get("area", "other"),
         "type": type_of[o], "individual": bool(vocab.get(o, {}).get("individual")),
         "ubiquitous": o in ubiquitous}
        for o in sorted(obj_df, key=lambda o: -obj_df[o])
    ]

    # vocab tree for the ontology browser (structures with a parent or children)
    vocab_tree = {o: {"parent": d.get("parent"), "area": d.get("area", "other")}
                  for o, d in vocab.items()
                  if d.get("type") == "structure" and d.get("df", 0) > 0}

    graph_local = {"nodes": nodes, "edges": edges, "objects": obj_table,
                   "relations": rel_edges, "vocabTree": vocab_tree}
    OUT_LOCAL.write_text(json.dumps(graph_local))

    # publish-safe variant: redact recovered statement text (metadata stays)
    safe_nodes = []
    n_redacted = 0
    for node in nodes:
        if node["src"] == "recovered":
            node = {**node, "text": WITHHELD_NOTE, "tex": ""}
            n_redacted += 1
        safe_nodes.append(node)
    graph = {**graph_local, "nodes": safe_nodes}
    OUT.write_text(json.dumps(graph))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB, {n_redacted} statements redacted) "
          f"and {OUT_LOCAL.name}: {len(nodes)} nodes, {len(edges)} edges, "
          f"{len(rel_edges)} relation edges, {len(obj_table)} objects")

    top = sorted(((sum(idf[o] ** 2 for _ in conj_of[o]) * 0, obj_df[o], o) for o in conj_of), reverse=True)[:20]
    print("\ntop objects by df (in projection):")
    for _, c, o in top:
        print(f"  {c:4d}  {o}")


if __name__ == "__main__":
    main()
