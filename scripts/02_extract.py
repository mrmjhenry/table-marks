#!/usr/bin/env python3
"""Stage 2: Extract mathematical objects from each conjecture with Claude.

Uses the Message Batches API (50% off) with structured outputs. Results are
appended to data/extractions.jsonl keyed by content_hash, so reruns only
process conjectures not yet extracted.

Usage:
  python scripts/02_extract.py --sync --limit 20   # dry run for prompt review
  python scripts/02_extract.py                     # submit + poll full batch
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
OUT = ROOT / "data" / "extractions.jsonl"
FAILURES = ROOT / "data" / "extract_failures.jsonl"
BATCH_STATE = ROOT / "data" / "batch_state.json"

MODEL = "claude-sonnet-5"
BATCH_CHUNK = 500

SYSTEM = [
    {
        "type": "text",
        "text": """You are a research mathematician indexing conjectures for a knowledge graph. Given a conjecture's title and statement, list the mathematical objects it concerns.

Rules:
1. Use standard, generic names in lowercase singular form: "elliptic curve", not "the elliptic curves E/Q in the statement".
2. Keep a qualifier in the name only when it denotes a genuinely different object ("moduli space of curves" is its own object; "finite poset" is a "poset" with qualifier "finite").
3. Return 2-8 objects, the most central first, marking each "primary" (the conjecture is fundamentally about it) or "secondary" (appears in the statement but is not the subject).
4. Exclude generic mathematical words — number, function, set, sequence, bound, constant, integer, proof — unless part of a standard compound object (L-function, zeta function, generating function, prime number is fine as "prime").
5. Prefer the standard community name over a paraphrase ("partially ordered set" → "poset", "symmetric group" not "permutation group of n letters").
6. If the text is not actually a mathematical conjecture, set looks_like_conjecture to false and still extract what objects you can.

Examples:

Title: The structure of FAC posets and the Aharoni--Korman conjecture
Statement: If a poset $P$ contains no infinite antichain then there exists a chain $C$ and a partition of $P$ into disjoint antichains $(A_i : i \\in I)$ such that each $A_i$ meets $C$.
Output: {"objects": [{"name": "poset", "qualifier": null, "centrality": "primary"}, {"name": "chain", "qualifier": null, "centrality": "primary"}, {"name": "antichain", "qualifier": "infinite", "centrality": "primary"}, {"name": "partition", "qualifier": null, "centrality": "secondary"}], "looks_like_conjecture": true}

Title: Ranks of elliptic curves in quadratic twist families
Statement: For any elliptic curve $E/\\mathbb{Q}$, the set of squarefree $d$ such that $\\mathrm{rank}(E_d) \\geq 2$ has density zero.
Output: {"objects": [{"name": "elliptic curve", "qualifier": "over Q", "centrality": "primary"}, {"name": "quadratic twist", "qualifier": null, "centrality": "primary"}, {"name": "Mordell-Weil rank", "qualifier": null, "centrality": "primary"}, {"name": "density", "qualifier": null, "centrality": "secondary"}], "looks_like_conjecture": true}

Title: Cohomology of moduli of stable curves
Statement: The tautological ring $R^*(\\overline{\\mathcal{M}}_{g,n})$ is Gorenstein.
Output: {"objects": [{"name": "moduli space of stable curves", "qualifier": null, "centrality": "primary"}, {"name": "tautological ring", "qualifier": null, "centrality": "primary"}, {"name": "Gorenstein ring", "qualifier": null, "centrality": "secondary"}, {"name": "cohomology", "qualifier": null, "centrality": "secondary"}], "looks_like_conjecture": true}""",
        "cache_control": {"type": "ephemeral"},
    }
]

SCHEMA = {
    "type": "object",
    "properties": {
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "qualifier": {"type": ["string", "null"]},
                    "centrality": {"type": "string", "enum": ["primary", "secondary"]},
                },
                "required": ["name", "qualifier", "centrality"],
                "additionalProperties": False,
            },
        },
        "looks_like_conjecture": {"type": "boolean"},
    },
    "required": ["objects", "looks_like_conjecture"],
    "additionalProperties": False,
}


def user_content(row) -> str:
    return f"Title: {row.title}\nStatement: {row.model_text}"


def request_params(row) -> MessageCreateParamsNonStreaming:
    return MessageCreateParamsNonStreaming(
        model=MODEL,
        max_tokens=1000,
        thinking={"type": "disabled"},
        system=SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": user_content(row)}],
    )


def load_done() -> set:
    done = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["content_hash"])
    return done


def append_jsonl(path: Path, record: dict):
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def run_sync(client, pending, limit):
    for row in pending.head(limit).itertuples():
        resp = client.messages.create(**request_params(row))
        text = next(b.text for b in resp.content if b.type == "text")
        data = json.loads(text)
        print(f"\n[{row.primary_category or '?'}] {row.title[:70]}")
        for o in data["objects"]:
            q = f" ({o['qualifier']})" if o["qualifier"] else ""
            print(f"  {o['centrality'][:3]}: {o['name']}{q}")
        if not data["looks_like_conjecture"]:
            print("  !! flagged as not a conjecture")


def submit_and_poll(client, pending):
    done = load_done()
    for start in range(0, len(pending), BATCH_CHUNK):
        chunk = pending.iloc[start : start + BATCH_CHUNK]
        requests = [
            Request(custom_id=row.content_hash, params=request_params(row))
            for row in chunk.itertuples()
        ]
        batch = client.messages.batches.create(requests=requests)
        BATCH_STATE.write_text(json.dumps({"batch_id": batch.id}))
        print(f"submitted batch {batch.id} ({len(requests)} requests)")

        while True:
            batch = client.messages.batches.retrieve(batch.id)
            if batch.processing_status == "ended":
                break
            c = batch.request_counts
            print(f"  …{batch.processing_status}: {c.succeeded} ok / {c.errored} err / {c.processing} pending")
            time.sleep(60)

        n_ok = n_err = 0
        for result in client.messages.batches.results(batch.id):
            chash = result.custom_id
            if result.result.type == "succeeded":
                msg = result.result.message
                text = next((b.text for b in msg.content if b.type == "text"), "")
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    append_jsonl(FAILURES, {"content_hash": chash, "error": "bad_json", "raw": text[:500]})
                    n_err += 1
                    continue
                if chash not in done:
                    append_jsonl(OUT, {"content_hash": chash, **data})
                    done.add(chash)
                n_ok += 1
            else:
                append_jsonl(FAILURES, {"content_hash": chash, "error": result.result.type})
                n_err += 1
        print(f"batch done: {n_ok} ok, {n_err} failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync", action="store_true", help="run direct calls instead of a batch")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    client = anthropic.Anthropic()
    df = pd.read_parquet(CONJECTURES)
    done = load_done()
    pending = df[~df["content_hash"].isin(done)]
    print(f"{len(df)} conjectures, {len(done)} already extracted, {len(pending)} pending")
    if pending.empty:
        return

    if args.sync:
        run_sync(client, pending, args.limit)
    else:
        submit_and_poll(client, pending)


if __name__ == "__main__":
    main()
