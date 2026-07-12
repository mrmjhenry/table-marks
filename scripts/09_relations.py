#!/usr/bin/env python3
"""Stage 9: Typed logical relations between conjecture pairs.

Candidates = top graph edges by weight + embedding near-duplicate pairs.
Each pair is classified by Claude (Batches API, resumable by pair key):
  generalizes | implies | equivalent | same_conjecture | none
with a `subject` saying which side generalizes/implies the other.

Output: data/relations.jsonl {a, b, relation, subject, justification}
"""
import argparse
import json
import time
from pathlib import Path

import anthropic
import pandas as pd
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

ROOT = Path(__file__).resolve().parent.parent
CONJECTURES = ROOT / "data" / "conjectures.parquet"
GRAPH = ROOT / "data" / "graph.json"
DUPS = ROOT / "data" / "dup_candidates.jsonl"
OUT = ROOT / "data" / "relations.jsonl"
FAILURES = ROOT / "data" / "relations_failures.jsonl"

MODEL = "claude-sonnet-5"
BATCH_CHUNK = 500
MAX_PAIRS = 6000

SYSTEM = [{
    "type": "text",
    "text": """You compare two mathematical conjectures, A and B, and decide their logical relationship. Be strict — most pairs merely share objects and have NO logical relation.

- "generalizes": one statement strictly subsumes the other (every instance of the narrower one is an instance of the broader one). Set subject to the BROADER side.
- "implies": the truth of one would establish the truth of the other (but they are not just special case/generalization). Set subject to the implying side.
- "equivalent": each implies the other (known or obvious equivalence).
- "same_conjecture": the same assertion, restated or trivially reformulated.
- "none": everything else — including 'related', 'analogous', 'same technique', 'same objects'. When in doubt, answer none.

Give a one-sentence justification. Do not speculate about deep unproven connections.""",
    "cache_control": {"type": "ephemeral"},
}]

SCHEMA = {
    "type": "object",
    "properties": {
        "relation": {"type": "string",
                     "enum": ["generalizes", "implies", "equivalent", "same_conjecture", "none"]},
        "subject": {"anyOf": [{"type": "string", "enum": ["a", "b"]}, {"type": "null"}]},
        "justification": {"type": "string"},
    },
    "required": ["relation", "subject", "justification"],
    "additionalProperties": False,
}

pkey = lambda a, b: a + "_" + b if a < b else b + "_" + a  # custom_id-safe separator


def request_params(ra, rb):
    content = (f"Conjecture A — {ra.title}\n{ra.model_text[:1800]}\n\n"
               f"Conjecture B — {rb.title}\n{rb.model_text[:1800]}")
    return MessageCreateParamsNonStreaming(
        model=MODEL, max_tokens=300, thinking={"type": "disabled"},
        system=SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": content}],
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    client = anthropic.Anthropic()
    df = pd.read_parquet(CONJECTURES).set_index("content_hash")

    graph = json.loads(GRAPH.read_text())
    edges = sorted(graph["edges"], key=lambda e: -e["w"])
    pairs = {}
    for e in edges[:MAX_PAIRS]:
        pairs[pkey(e["s"], e["t"])] = (e["s"], e["t"])
    if DUPS.exists():
        for line in DUPS.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                pairs[pkey(d["a"], d["b"])] = (d["a"], d["b"])

    done = set()
    if OUT.exists():
        done = {pkey(r["a"], r["b"]) for r in map(json.loads, OUT.read_text().splitlines()) if r}
    pending = [(k, ab) for k, ab in pairs.items()
               if k not in done and ab[0] in df.index and ab[1] in df.index]
    print(f"{len(pairs)} candidate pairs, {len(done)} classified, {len(pending)} pending")
    if not pending:
        return

    if args.sync:
        for k, (a, b) in pending[:args.limit]:
            resp = client.messages.create(**request_params(df.loc[a], df.loc[b]))
            d = json.loads(next(bk.text for bk in resp.content if bk.type == "text"))
            print(f"{d['relation']:15s} {df.loc[a].title[:40]} <-> {df.loc[b].title[:40]}")
            if d["relation"] != "none":
                print(f"   {d['justification']}")
        return

    for start in range(0, len(pending), BATCH_CHUNK):
        chunk = pending[start : start + BATCH_CHUNK]
        reqs = [Request(custom_id=k, params=request_params(df.loc[a], df.loc[b]))
                for k, (a, b) in chunk]
        batch = client.messages.batches.create(requests=reqs)
        print(f"submitted {batch.id} ({len(reqs)})")
        while True:
            batch = client.messages.batches.retrieve(batch.id)
            if batch.processing_status == "ended":
                break
            time.sleep(60)
        kmap = dict(chunk)
        n_rel = 0
        for result in client.messages.batches.results(batch.id):
            k = result.custom_id
            a, b = kmap[k]
            if result.result.type != "succeeded":
                with FAILURES.open("a") as f:
                    f.write(json.dumps({"a": a, "b": b, "error": result.result.type}) + "\n")
                continue
            text = next((bk.text for bk in result.result.message.content if bk.type == "text"), "")
            try:
                d = json.loads(text)
            except json.JSONDecodeError:
                continue
            if k not in done:
                with OUT.open("a") as f:
                    f.write(json.dumps({"a": a, "b": b, **d}) + "\n")
                done.add(k)
                n_rel += d["relation"] != "none"
        print(f"  chunk done, {n_rel} non-none relations")

    recs = [json.loads(l) for l in OUT.read_text().splitlines() if l.strip()]
    from collections import Counter
    print(Counter(r["relation"] for r in recs))


if __name__ == "__main__":
    main()
