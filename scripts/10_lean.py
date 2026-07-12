#!/usr/bin/env python3
"""Stage 10: Lean/mathlib formalization signal per conjecture.

For each conjecture: query LeanSearch (semantic search over mathlib) with the
title+statement, prefilter hits by embedding similarity between the statement
and each hit's informal description, then LLM-verify plausible hits.

Status per conjecture:
  statement_found — a mathlib declaration formalizes this statement (verified)
  related         — closely related mathlib material (high-sim hit, not the statement)
  none            — nothing close in mathlib

Caveat (documented in README): this checks MATHLIB only. Formalizations living
in standalone Lean repos (e.g. the Aharoni–Korman counterexample) are not
indexed by LeanSearch and will not be found.

Output: data/lean.jsonl {content_hash, status, decl, module, sim}
"""
import json
import time
import urllib.request
from pathlib import Path

import anthropic
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CONJECTURES = ROOT / "data" / "conjectures.parquet"
EMB = ROOT / "data" / "embeddings.npy"
EMB_IDS = ROOT / "data" / "embedding_ids.json"
CACHE = ROOT / "data" / "leansearch_cache.jsonl"
VCACHE = ROOT / "data" / "lean_verify_cache.jsonl"
OUT = ROOT / "data" / "lean.jsonl"

API = "https://leansearch.net/search"
DELAY_S = 1.2
SIM_RELATED = 0.72
LLM = "claude-sonnet-5"

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "formalizes_statement": {"type": "boolean"},
        "note": {"type": "string"},
    },
    "required": ["formalizes_statement", "note"],
    "additionalProperties": False,
}


def leansearch(query: str):
    body = json.dumps({"query": [query[:400]], "num_results": 5}).encode()
    req = urllib.request.Request(API, data=body,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "openconjecture-map/1.0 (personal research)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        results = json.loads(r.read())
    hits = []
    for item in results[0]:
        r_ = item.get("result", {})
        hits.append({
            "decl": ".".join(r_.get("name") or []),
            "module": ".".join(r_.get("module_name") or []),
            "kind": r_.get("kind"),
            "informal": (r_.get("informal_description") or r_.get("informal_name") or "")[:600],
        })
    return hits


def main():
    df = pd.read_parquet(CONJECTURES)
    ids = json.loads(EMB_IDS.read_text())
    X = np.load(EMB)
    row_of = {h: i for i, h in enumerate(ids)}

    cached = {}
    if CACHE.exists():
        for l in CACHE.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                cached[r["content_hash"]] = r["hits"]

    # ---- 1. query LeanSearch (cached, rate-limited) ----
    pending = df[~df.content_hash.isin(cached)]
    print(f"{len(df)} conjectures, {len(cached)} leansearch-cached, {len(pending)} to query")
    for n, row in enumerate(pending.itertuples()):
        try:
            hits = leansearch(f"{row.title}. {row.display_text[:300]}")
        except Exception as e:
            print(f"  query failed ({e}); retrying once in 30s")
            time.sleep(30)
            try:
                hits = leansearch(f"{row.title}. {row.display_text[:300]}")
            except Exception:
                hits = []
        with CACHE.open("a") as f:
            f.write(json.dumps({"content_hash": row.content_hash, "hits": hits}) + "\n")
        cached[row.content_hash] = hits
        time.sleep(DELAY_S)
        if (n + 1) % 100 == 0:
            print(f"  …{n + 1}/{len(pending)} queried")

    # ---- 2. embedding prefilter ----
    from sentence_transformers import SentenceTransformer
    st = SentenceTransformer("all-MiniLM-L6-v2")
    candidates = []  # (chash, hit, sim)
    best_related = {}
    informal_texts, keys = [], []
    for chash, hits in cached.items():
        for h in hits:
            if h["informal"]:
                informal_texts.append(h["informal"])
                keys.append((chash, h))
    H = st.encode(informal_texts, batch_size=128, normalize_embeddings=True,
                  show_progress_bar=True)
    for (chash, h), hv in zip(keys, H):
        if chash not in row_of:
            continue
        sim = float(X[row_of[chash]] @ hv)
        if sim >= SIM_RELATED:
            prev = best_related.get(chash)
            if not prev or sim > prev[1]:
                best_related[chash] = (h, sim)
    print(f"{len(best_related)} conjectures with a high-similarity mathlib hit")

    # ---- 3. LLM verification of high-sim hits (incrementally cached) ----
    client = anthropic.Anthropic()
    results = {}
    if VCACHE.exists():
        for l in VCACHE.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                results[r.pop("content_hash")] = r
    items = sorted(best_related.items(), key=lambda kv: -kv[1][1])
    dfi = df.set_index("content_hash")
    for i, (chash, (h, sim)) in enumerate(items):
        if chash in results:
            continue
        row = dfi.loc[chash]
        resp = client.messages.create(
            model=LLM, max_tokens=300, thinking={"type": "disabled"},
            output_config={"format": {"type": "json_schema", "schema": VERIFY_SCHEMA}},
            messages=[{"role": "user", "content":
                f"Conjecture: {row.title}\n{row.display_text[:1200]}\n\n"
                f"Mathlib declaration `{h['decl']}` ({h['kind']}):\n{h['informal']}\n\n"
                "Does this mathlib declaration formalize THE STATEMENT of the conjecture "
                "(as a stated theorem/conjecture), as opposed to merely defining or proving "
                "something about the objects involved?"}],
        )
        d = json.loads(next(b.text for b in resp.content if b.type == "text"))
        results[chash] = {
            "status": "statement_found" if d["formalizes_statement"] else "related",
            "decl": h["decl"], "module": h["module"], "sim": round(sim, 3),
            "note": d["note"],
        }
        with VCACHE.open("a") as f:
            f.write(json.dumps({"content_hash": chash, **results[chash]}) + "\n")
        if (i + 1) % 50 == 0:
            print(f"  …verified {i + 1}/{len(items)}")

    with OUT.open("w") as f:
        for chash in df.content_hash:
            rec = results.get(chash, {"status": "none"})
            f.write(json.dumps({"content_hash": chash, **rec}) + "\n")

    from collections import Counter
    print(Counter(r["status"] for r in results.values()) or "no hits at all")
    found = [(c, r) for c, r in results.items() if r["status"] == "statement_found"]
    for c, r in found[:15]:
        print(f"  FORMALIZED: {dfi.loc[c].title[:60]} -> {r['decl']}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
