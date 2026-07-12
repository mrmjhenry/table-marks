#!/usr/bin/env python3
"""Stage 8: Embedding clusters — a taxonomy-free topic lens.

Embeds title + statement with a local sentence-transformer, clusters with
HDBSCAN, names each cluster with one Claude call over its central members.
Also emits high-similarity pairs (data/dup_candidates.jsonl) used by
09_relations.py as extra candidates.

Outputs: data/embeddings.npy (row order = data/embedding_ids.json),
         data/clusters.jsonl {content_hash, cluster_id, cluster_name},
         data/dup_candidates.jsonl {a, b, sim}
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

import anthropic
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CONJECTURES = ROOT / "data" / "conjectures.parquet"
EMB = ROOT / "data" / "embeddings.npy"
EMB_IDS = ROOT / "data" / "embedding_ids.json"
OUT = ROOT / "data" / "clusters.jsonl"
DUPS = ROOT / "data" / "dup_candidates.jsonl"

MODEL_NAME = "all-MiniLM-L6-v2"
LLM = "claude-sonnet-5"
DUP_SIM = 0.93

NAME_SCHEMA = {
    "type": "object",
    "properties": {
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cluster_id": {"type": "integer"},
                    "name": {"type": "string"},
                },
                "required": ["cluster_id", "name"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clusters"],
    "additionalProperties": False,
}


def main():
    df = pd.read_parquet(CONJECTURES)
    texts = (df.title + ". " + df.display_text.str.slice(0, 1200)).tolist()
    ids = df.content_hash.tolist()

    # ---- embeddings (cached) ----
    if EMB.exists() and EMB_IDS.exists() and json.loads(EMB_IDS.read_text()) == ids:
        X = np.load(EMB)
        print(f"loaded cached embeddings {X.shape}")
    else:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(MODEL_NAME)
        X = model.encode(texts, batch_size=64, show_progress_bar=True,
                         normalize_embeddings=True)
        np.save(EMB, X)
        EMB_IDS.write_text(json.dumps(ids))
        print(f"embedded {X.shape}")

    # ---- near-duplicate candidates for 09_relations ----
    sims = X @ X.T
    np.fill_diagonal(sims, 0)
    ii, jj = np.where(sims >= DUP_SIM)
    with DUPS.open("w") as f:
        seen = set()
        for i, j in zip(ii, jj):
            key = (min(i, j), max(i, j))
            if key in seen:
                continue
            seen.add(key)
            f.write(json.dumps({"a": ids[key[0]], "b": ids[key[1]],
                                "sim": round(float(sims[key[0], key[1]]), 4)}) + "\n")
    print(f"{len(seen)} near-duplicate candidate pairs (sim >= {DUP_SIM})")

    # ---- clustering ----
    from sklearn.cluster import HDBSCAN
    labels = HDBSCAN(min_cluster_size=5, min_samples=2, metric="euclidean",
                     cluster_selection_method="leaf") \
        .fit_predict(X)
    n_clusters = labels.max() + 1
    noise = int((labels == -1).sum())
    print(f"{n_clusters} clusters, {noise} noise points ({100*noise/len(labels):.0f}%)")

    # ---- name clusters (central members by distance to centroid) ----
    client = anthropic.Anthropic()
    members = defaultdict(list)
    for idx, lab in enumerate(labels):
        if lab >= 0:
            members[int(lab)].append(idx)
    reps = {}
    for lab, idxs in members.items():
        centroid = X[idxs].mean(axis=0)
        d = X[idxs] @ centroid
        order = np.argsort(-d)
        reps[lab] = [df.iloc[idxs[k]].title for k in order[:8]]

    names = {}
    labs = sorted(reps)
    for i in range(0, len(labs), 25):
        block = labs[i : i + 25]
        prompt = ("Name each cluster of mathematical conjectures with a short, specific topic "
                  "label (2-5 words, lowercase, e.g. 'graph coloring', 'moduli of curves', "
                  "'random matrix spectra'). Base the name on the member titles.\n\n")
        for lab in block:
            prompt += f"cluster_id {lab}:\n" + "\n".join(f"  - {t[:100]}" for t in reps[lab]) + "\n\n"
        resp = client.messages.create(
            model=LLM, max_tokens=2000, thinking={"type": "disabled"},
            output_config={"format": {"type": "json_schema", "schema": NAME_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        for c in json.loads(next(b.text for b in resp.content if b.type == "text"))["clusters"]:
            names[c["cluster_id"]] = c["name"]
        print(f"  named {len(names)}/{n_clusters}")

    with OUT.open("w") as f:
        for idx, lab in enumerate(labels):
            f.write(json.dumps({
                "content_hash": ids[idx],
                "cluster_id": int(lab),
                "cluster_name": names.get(int(lab), "") if lab >= 0 else "",
            }) + "\n")

    sizes = Counter(int(l) for l in labels if l >= 0)
    print("\nlargest clusters:")
    for lab, size in sizes.most_common(15):
        print(f"  {size:4d}  {names.get(lab, '?')}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
