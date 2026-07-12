#!/usr/bin/env python3
"""Stage 7: Assign MSC 2020 subject codes to each conjecture.

Batch job (same resumable pattern as 02): keyed by content_hash into
data/msc.jsonl. Each conjecture gets 1-2 five-char MSC codes, validated
against vendor/msc2020.json; invalid leaves fall back to their 3-char class.
Context includes the paper's abstract (papers config, joined on arxiv_id).
"""
import argparse
import json
import re
import time
from pathlib import Path

import anthropic
import pandas as pd
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from datasets import load_dataset

ROOT = Path(__file__).resolve().parent.parent
CONJECTURES = ROOT / "data" / "conjectures.parquet"
MSC_FILE = ROOT / "vendor" / "msc2020.json"
OUT = ROOT / "data" / "msc.jsonl"
FAILURES = ROOT / "data" / "msc_failures.jsonl"

MODEL = "claude-sonnet-5"
BATCH_CHUNK = 500

MSC = json.loads(MSC_FILE.read_text())

SYSTEM = [
    {
        "type": "text",
        "text": """You are a zbMATH/MathSciNet subject-classification expert. Given a mathematical conjecture (title, statement, and the abstract of the paper it appears in), assign 1-2 MSC 2020 classification codes for the CONJECTURE itself (not the whole paper).

Rules:
1. Use full five-character codes (e.g. 05C15, 11G05, 14J28). The first code is the primary classification.
2. Choose the most specific code that genuinely fits; do not force specificity that isn't there.
3. Add a second code only when the conjecture genuinely spans two areas.
4. Use standard MSC 2020 codes only.""",
        "cache_control": {"type": "ephemeral"},
    }
]

SCHEMA = {
    "type": "object",
    "properties": {
        "codes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["codes"],
    "additionalProperties": False,
}


def validate(codes):
    """Return valid codes; invalid 5-char leaves fall back to their 3-char class."""
    out = []
    for c in codes[:2]:
        c = c.strip().upper().replace(" ", "")
        if c in MSC:
            out.append(c)
        elif re.fullmatch(r"\d{2}[A-Z]\d{2}", c) and (c[:3] + "xx") in MSC:
            out.append(c[:3] + "xx")
        elif re.fullmatch(r"\d{2}", c) and (c + "-XX") in MSC:
            out.append(c + "-XX")
    return list(dict.fromkeys(out))


def request_params(row, abstract):
    content = f"Title: {row.title}\nStatement: {row.model_text}"
    if abstract:
        content += f"\nPaper abstract: {abstract[:1500]}"
    return MessageCreateParamsNonStreaming(
        model=MODEL, max_tokens=200, thinking={"type": "disabled"},
        system=SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": content}],
    )


def load_done():
    if not OUT.exists():
        return set()
    return {json.loads(l)["content_hash"] for l in OUT.read_text().splitlines() if l.strip()}


def append(path, rec):
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    client = anthropic.Anthropic()
    df = pd.read_parquet(CONJECTURES)
    papers = load_dataset("davisrbr/openconjecture", "papers", split="train").to_pandas()
    abstract_of = papers.set_index("arxiv_id")["summary"].to_dict()

    done = load_done()
    pending = df[~df.content_hash.isin(done)]
    print(f"{len(df)} conjectures, {len(done)} coded, {len(pending)} pending")
    if pending.empty:
        return

    if args.sync:
        for row in pending.head(args.limit).itertuples():
            resp = client.messages.create(**request_params(row, abstract_of.get(row.arxiv_id)))
            data = json.loads(next(b.text for b in resp.content if b.type == "text"))
            codes = validate(data["codes"])
            print(f"[{row.primary_category or '?'}] {row.title[:60]}")
            for c in codes:
                print(f"   {c}  {MSC.get(c)}")
        return

    n_valid = n_empty = 0
    for start in range(0, len(pending), BATCH_CHUNK):
        chunk = pending.iloc[start : start + BATCH_CHUNK]
        reqs = [Request(custom_id=r.content_hash,
                        params=request_params(r, abstract_of.get(r.arxiv_id)))
                for r in chunk.itertuples()]
        batch = client.messages.batches.create(requests=reqs)
        print(f"submitted {batch.id} ({len(reqs)} requests)")
        while True:
            batch = client.messages.batches.retrieve(batch.id)
            if batch.processing_status == "ended":
                break
            time.sleep(45)
        for result in client.messages.batches.results(batch.id):
            chash = result.custom_id
            if result.result.type != "succeeded":
                append(FAILURES, {"content_hash": chash, "error": result.result.type})
                continue
            text = next((b.text for b in result.result.message.content if b.type == "text"), "")
            try:
                raw = json.loads(text)["codes"]
            except (json.JSONDecodeError, KeyError):
                append(FAILURES, {"content_hash": chash, "error": "bad_json"})
                continue
            codes = validate(raw)
            if chash not in done:
                append(OUT, {"content_hash": chash, "codes": codes,
                             "names": [MSC.get(c, "") for c in codes], "raw": raw})
                done.add(chash)
            n_valid += bool(codes)
            n_empty += not codes
        print(f"  progress: {len(done)} coded ({n_empty} with no valid code)")

    print(f"done: {len(done)} total, {n_empty} empty after validation")


if __name__ == "__main__":
    main()
