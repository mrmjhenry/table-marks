#!/usr/bin/env python3
"""Stage 11: Bridge-objects report — which entities connect distant fields?

For each entity (structures only — properties can't be 'bridges' in a
meaningful sense), compute the Shannon entropy of the top-level MSC classes of
the conjectures it appears in. High-df, high-entropy entities are the bridges.

Output: reports/bridge_objects.md
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
MSC_ASSIGN = ROOT / "data" / "msc.jsonl"
MSC_NAMES = ROOT / "vendor" / "msc2020.json"
OUT = ROOT / "reports" / "bridge_objects.md"

MIN_DF = 8


def entropy(counter):
    n = sum(counter.values())
    return -sum((c / n) * math.log2(c / n) for c in counter.values() if c)


def main():
    df = pd.read_parquet(CONJECTURES).set_index("content_hash")
    vocab = json.loads(VOCAB.read_text())
    msc_names = json.loads(MSC_NAMES.read_text())

    msc_of = {}
    for l in MSC_ASSIGN.read_text().splitlines():
        if l.strip():
            r = json.loads(l)
            if r["codes"]:
                msc_of[r["content_hash"]] = r["codes"][0][:2]  # top-level class

    objects_of = {}
    for l in NORMALIZED.read_text().splitlines():
        if l.strip():
            r = json.loads(l)
            objects_of[r["content_hash"]] = r["objects"]

    classes_of_obj = defaultdict(Counter)
    titles_of_obj = defaultdict(list)
    for chash, objs in objects_of.items():
        cls = msc_of.get(chash)
        if not cls or chash not in df.index:
            continue
        for o in objs:
            if vocab.get(o, {}).get("type") == "structure":
                classes_of_obj[o][cls] += 1
                titles_of_obj[o].append(chash)

    rows = []
    for o, cnt in classes_of_obj.items():
        n = sum(cnt.values())
        if n < MIN_DF:
            continue
        rows.append({"entity": o, "df": n, "entropy": entropy(cnt),
                     "n_classes": len(cnt), "classes": cnt})
    rows.sort(key=lambda r: -(r["entropy"] * math.log(r["df"])))

    lines = [
        "# Bridge entities",
        "",
        "Which mathematical structures connect otherwise-distant fields? For each",
        "structure appearing in ≥ %d MSC-classified conjectures, we compute the" % MIN_DF,
        "Shannon entropy of the top-level MSC classes of those conjectures.",
        "High df × high entropy = a bridge. (Structures only — invariants and",
        "properties are excluded; 'isomorphism' bridging fields is not news.)",
        "",
        "| rank | entity | conjectures | MSC classes | entropy (bits) | class spread |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows[:40], 1):
        spread = ", ".join(
            f"{c} {msc_names.get(c + '-XX', c)} ({k})"
            for c, k in r["classes"].most_common(4))
        lines.append(f"| {i} | **{r['entity']}** | {r['df']} | {r['n_classes']} "
                     f"| {r['entropy']:.2f} | {spread[:140]} |")

    lines += ["", "## Examples for the top 5 bridges", ""]
    for r in rows[:5]:
        lines.append(f"### {r['entity']}")
        by_cls = defaultdict(list)
        for chash in titles_of_obj[r["entity"]]:
            by_cls[msc_of[chash]].append(df.loc[chash].title)
        for cls, ts in sorted(by_cls.items(), key=lambda kv: -len(kv[1]))[:4]:
            nm = msc_names.get(cls + "-XX", cls)
            lines.append(f"- *{cls} — {nm}*: " + "; ".join(f"“{t[:70]}”" for t in ts[:2]))
        lines.append("")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT} ({len(rows)} entities ranked)")
    for r in rows[:10]:
        print(f"  {r['entropy']:.2f} bits, df {r['df']:3d}: {r['entity']}")


if __name__ == "__main__":
    main()
