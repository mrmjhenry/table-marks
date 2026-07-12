#!/usr/bin/env python3
"""Stage 3b: Assign a type to every canonical vocabulary entry.

Types (Frege-inspired; see README § What we mean by "entity"):
  structure  — saturated kind of mathematical thing (poset, elliptic curve)
  invariant  — quantity/function OF a structure (chromatic number, genus)
  property   — predicate or relation (log concavity, isomorphism)
  statement  — named theorem/conjecture/hypothesis (Riemann hypothesis)
  discarded  — proof techniques and non-entities (polynomial method)

Also flags individuals (specific instances: "the Monster group", "pi") vs kinds.

Reads data/vocab.json + context titles; writes `type`/`individual` back into
data/vocab.json (idempotent — entries already typed are skipped) and appends a
type report to data/review_types.txt.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

import anthropic
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
VOCAB = ROOT / "data" / "vocab.json"
NORMALIZED = ROOT / "data" / "normalized.jsonl"
CONJECTURES = ROOT / "data" / "conjectures.parquet"
REVIEW = ROOT / "data" / "review_types.txt"

MODEL = "claude-sonnet-5"
CHUNK = 100

TYPES = ["structure", "invariant", "property", "statement", "discarded"]

SYSTEM = """You classify entries of a vocabulary of mathematical entities extracted from conjecture statements. Assign each term exactly one type:

- "structure": a saturated kind of mathematical thing — something you can exhibit an instance of. Examples: poset, elliptic curve, K3 surface, Cayley graph, matroid, Banach space, permutation, prime.
- "invariant": a quantity, number, or function attached TO a structure — it has an implicit argument slot ("the ___ of X"). Examples: chromatic number, genus, Mordell-Weil rank, eigenvalue, partition function, entropy.
- "property": a predicate or relation that holds OF structures. Examples: log concavity, isomorphism, edge-expansion, density, planarity, congruence, Gorenstein.
- "statement": a NAMED theorem, conjecture, hypothesis, equation, or principle referred to as a thing. Examples: Riemann hypothesis, ABC conjecture, Einstein vacuum equations, four color theorem.
- "discarded": proof techniques and methods (polynomial method, circle method, sieve), meta-mathematical words (proof, counterexample, bound, upper bound, formula), or garbled non-entities.

Also set "individual": true when the term names one specific instance rather than a kind — e.g. "Monster group", "Petersen graph", "Riemann zeta function" are individuals; "sporadic group", "cubic graph", "L-function" are kinds. Named statements are always individual. Default false when unsure.

Edge guidance: named function families used as objects of study ("zeta function", "modular form") are structures; a specific named one ("Riemann zeta function") is an individual structure. Numbers-as-quantities ("independence number") are invariants; number kinds ("prime", "perfect number") are structures. When a term could be read as structure or invariant, prefer how it is used in the example conjecture titles provided."""

SCHEMA = {
    "type": "object",
    "properties": {
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "type": {"type": "string", "enum": TYPES},
                    "individual": {"type": "boolean"},
                },
                "required": ["term", "type", "individual"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["assignments"],
    "additionalProperties": False,
}


def main():
    client = anthropic.Anthropic()
    vocab = json.loads(VOCAB.read_text())

    # context: up to 3 conjecture titles per term
    titles = pd.read_parquet(CONJECTURES, columns=["content_hash", "title"]) \
        .set_index("content_hash")["title"].to_dict()
    examples = defaultdict(list)
    for line in NORMALIZED.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        t = titles.get(rec["content_hash"])
        if t:
            for o in rec["objects"]:
                if len(examples[o]) < 3:
                    examples[o].append(t)

    pending = sorted(t for t, d in vocab.items() if "type" not in d)
    print(f"{len(vocab)} vocab entries, {len(pending)} untyped")

    for i in range(0, len(pending), CHUNK):
        chunk = pending[i : i + CHUNK]
        lines = []
        for t in chunk:
            ex = "; ".join(examples.get(t, [])[:2])
            lines.append(f"- {t}" + (f"  [appears in: {ex[:180]}]" if ex else ""))
        resp = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            thinking={"type": "disabled"},
            system=SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": "TERMS:\n" + "\n".join(lines)}],
        )
        data = json.loads(next(b.text for b in resp.content if b.type == "text"))
        n = 0
        for a in data["assignments"]:
            term = a["term"].strip().lower()
            if term in vocab and "type" not in vocab[term]:
                vocab[term]["type"] = a["type"]
                vocab[term]["individual"] = bool(a["individual"])
                n += 1
        VOCAB.write_text(json.dumps(vocab, indent=1))  # checkpoint each chunk
        print(f"  chunk {i // CHUNK + 1}/{(len(pending) + CHUNK - 1) // CHUNK}: typed {n}/{len(chunk)}")

    missing = [t for t, d in vocab.items() if "type" not in d]
    for t in missing:  # model skipped it — default conservatively
        vocab[t]["type"] = "structure"
        vocab[t]["individual"] = False
    if missing:
        print(f"defaulted {len(missing)} skipped terms to structure: {missing[:10]}")
    VOCAB.write_text(json.dumps(vocab, indent=1))

    # report
    dist = Counter(d["type"] for d in vocab.values())
    ind = sum(1 for d in vocab.values() if d.get("individual"))
    lines = ["== type distribution =="]
    for t in TYPES:
        lines.append(f"{t:10s} {dist.get(t, 0):5d}")
    lines.append(f"individuals: {ind}")
    for t in TYPES:
        members = sorted(((d.get('df', 0), k) for k, d in vocab.items() if d['type'] == t), reverse=True)
        lines.append(f"\n== top {t} ==")
        for df, k in members[:15]:
            flag = " (individual)" if vocab[k].get("individual") else ""
            lines.append(f"{df:5d}  {k}{flag}")
    REVIEW.write_text("\n".join(lines))
    print("\n".join(lines[:8]))
    print(f"wrote {REVIEW}")


if __name__ == "__main__":
    main()
