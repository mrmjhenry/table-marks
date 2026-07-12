#!/usr/bin/env python3
"""Stage 3: Canonicalize extracted object names into a vocabulary.

Pass A (mechanical): case/TeX folding + rule-based singularization → raw terms.
Pass B (LLM): merge duplicate anchors, map tail terms onto anchors, assign areas.

Outputs:
  data/raw_terms.tsv        term<TAB>document-frequency, for review
  data/vocab.json           canonical name -> {aliases, area, parent, df}
  data/normalized.jsonl     content_hash -> [canonical object names]
  data/normalize_review.txt flags for eyeball review
"""
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
EXTRACTIONS = ROOT / "data" / "extractions.jsonl"
RAW_TERMS = ROOT / "data" / "raw_terms.tsv"
VOCAB = ROOT / "data" / "vocab.json"
NORMALIZED = ROOT / "data" / "normalized.jsonl"
REVIEW = ROOT / "data" / "review_normalize.txt"

MODEL = "claude-sonnet-5"
ANCHOR_MIN_DF = 3
TAIL_CHUNK = 100

AREAS = [
    "combinatorics", "graph theory", "number theory", "algebraic geometry",
    "differential geometry", "topology", "group theory", "representation theory",
    "algebra", "analysis", "probability", "dynamical systems", "logic",
    "mathematical physics", "geometry", "category theory", "optimization",
    "theoretical computer science", "numerical analysis", "other",
]

SINGULAR_EXCEPTIONS = {
    "series", "calculus", "genus", "modulus", "locus", "basis", "analysis",
    "hypothesis", "axis", "matrix", "vertex", "simplex", "index", "apex",
    "torus", "annulus", "radius", "nexus", "gauss",
}


def fold(name: str) -> str:
    s = unicodedata.normalize("NFC", name).lower().strip()
    s = re.sub(r"[\$\\{}]", "", s)  # TeX remnants
    s = re.sub(r"^(the|a|an)\s+", "", s)
    s = re.sub(r"\s+", " ", s).strip(" .,;:")
    # singularize last word only
    words = s.split(" ")
    last = words[-1]
    if last not in SINGULAR_EXCEPTIONS and last.isalpha():
        if last.endswith("ies") and len(last) > 4:
            last = last[:-3] + "y"
        elif last.endswith(("ches", "shes", "xes", "sses")):
            last = last[:-2]
        elif last.endswith("s") and not last.endswith(("ss", "us", "is")):
            last = last[:-1]
    words[-1] = last
    return " ".join(words)


def llm_json(client, prompt: str, schema: dict) -> dict:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "disabled"},
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("response truncated at max_tokens — reduce chunk size")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


MERGE_SCHEMA = {
    "type": "object",
    "properties": {
        "merges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "keep": {"type": "string"},
                    "merge_in": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["keep", "merge_in"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["merges"],
    "additionalProperties": False,
}

MAP_SCHEMA = {
    "type": "object",
    "properties": {
        "mappings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "action": {"type": "string", "enum": ["map_to", "new_canonical", "discard"]},
                    "map_to": {"type": ["string", "null"]},
                },
                "required": ["term", "action", "map_to"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["mappings"],
    "additionalProperties": False,
}

AREA_SCHEMA = {
    "type": "object",
    "properties": {
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "area": {"type": "string", "enum": AREAS},
                    "parent_object": {"type": ["string", "null"]},
                },
                "required": ["term", "area", "parent_object"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["assignments"],
    "additionalProperties": False,
}


def main():
    client = anthropic.Anthropic()

    # incremental: reuse decisions from a previous run
    old_vocab = json.loads(VOCAB.read_text()) if VOCAB.exists() else {}
    known_alias = {a: c for c, d in old_vocab.items() for a in d.get("aliases", [])}

    # ---- Pass A: mechanical folding ----
    per_conj = {}  # content_hash -> list of folded terms
    df_counter = Counter()
    for line in EXTRACTIONS.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        terms = []
        for o in rec.get("objects", []):
            t = fold(o["name"])
            if len(t) >= 3:
                terms.append(t)
        terms = sorted(set(terms))
        per_conj[rec["content_hash"]] = terms
        df_counter.update(terms)

    RAW_TERMS.write_text(
        "\n".join(f"{t}\t{c}" for t, c in df_counter.most_common())
    )
    print(f"Pass A: {len(df_counter)} distinct folded terms across {len(per_conj)} conjectures")

    anchors = sorted(t for t, c in df_counter.items() if c >= ANCHOR_MIN_DF)
    tail = sorted(t for t, c in df_counter.items() if c < ANCHOR_MIN_DF)
    print(f"anchors (df>={ANCHOR_MIN_DF}): {len(anchors)}, tail: {len(tail)}")

    # ---- Pass B1: merge duplicate anchors ----
    alias_of = dict(known_alias)  # folded term -> canonical (seeded from prior run)
    new_anchor_set = {a for a in anchors if a not in old_vocab and a not in known_alias}
    marked = [(("* " + a) if a in new_anchor_set else a) for a in anchors]
    merge_result = llm_json(
        client,
        "These are mathematical object names extracted from conjectures; names marked with * are NEW. "
        "Identify groups that name the SAME mathematical object (synonyms, notation variants, "
        "abbreviations — e.g. 'poset' and 'partially ordered set'). Do NOT merge distinct objects "
        "that are merely related (e.g. 'graph' and 'directed graph' stay separate). "
        "Return ONLY groups that include at least one NEW (*) name, choosing the most standard "
        "name as 'keep' (without the * marker).\n\n"
        + "\n".join(marked),
        MERGE_SCHEMA,
    ) if new_anchor_set else {"merges": []}
    for m in merge_result["merges"]:
        keep = fold(m["keep"])
        if keep not in df_counter:
            continue
        for other in m["merge_in"]:
            other = fold(other)
            if other in df_counter and other != keep:
                alias_of[other] = keep
    canonical_anchors = sorted({alias_of.get(a, a) for a in anchors})
    print(f"Pass B1: merged {len(alias_of)} anchor aliases → {len(canonical_anchors)} canonical anchors")

    # ---- Pass B2: map tail terms onto anchors (new terms only) ----
    anchor_list = "\n".join(canonical_anchors)
    known = set(old_vocab) | set(known_alias) | set(alias_of)
    new_tail = [t for t in tail if t not in known]
    print(f"tail terms: {len(tail)} total, {len(new_tail)} new (rest reuse prior decisions)")
    n_map = n_new = n_discard = 0
    for i in range(0, len(new_tail), TAIL_CHUNK):
        chunk = new_tail[i : i + TAIL_CHUNK]
        result = llm_json(
            client,
            "Canonical vocabulary of mathematical objects:\n" + anchor_list
            + "\n\nFor each TERM below decide:\n"
            "- action 'map_to' + map_to=<vocabulary entry> if it names the same object as a vocabulary entry "
            "(or a minor variant of one);\n"
            "- action 'new_canonical' if it is a genuinely distinct, well-defined mathematical object not in the vocabulary;\n"
            "- action 'discard' if it is too vague, generic, not a mathematical object, or garbled.\n\n"
            "TERMS:\n" + "\n".join(chunk),
            MAP_SCHEMA,
        )
        seen_in_chunk = set()
        for m in result["mappings"]:
            t = fold(m["term"])
            if t not in df_counter or t in seen_in_chunk or t in alias_of:
                continue
            seen_in_chunk.add(t)
            if m["action"] == "map_to" and m["map_to"]:
                target = fold(m["map_to"])
                if target in canonical_anchors and target != t:
                    alias_of[t] = target
                    n_map += 1
                else:
                    n_discard += 1  # invalid target — treat as discard
                    alias_of[t] = None
            elif m["action"] == "new_canonical":
                n_new += 1
            else:
                alias_of[t] = None
                n_discard += 1
        print(f"  tail chunk {i // TAIL_CHUNK + 1}: mapped so far {n_map}, new {n_new}, discarded {n_discard}")

    # unmapped tail terms (model said new_canonical, or missing from responses) stay canonical
    canonicals = dict.fromkeys(canonical_anchors)
    for t in tail:
        if t not in alias_of:
            canonicals[t] = None
    canonicals = sorted(canonicals)
    print(f"Pass B2: {len(canonicals)} canonical objects total")

    # ---- Pass B3: assign areas + parent objects (new canonicals only) ----
    area_of = {c: old_vocab[c]["area"] for c in canonicals if c in old_vocab}
    parent_of = {c: old_vocab[c].get("parent") for c in canonicals if c in old_vocab}
    new_canon = [c for c in canonicals if c not in old_vocab]
    for i in range(0, len(new_canon), TAIL_CHUNK):
        chunk = new_canon[i : i + TAIL_CHUNK]
        result = llm_json(
            client,
            "For each mathematical object below, assign the mathematical area it most belongs to "
            f"(one of: {', '.join(AREAS)}), and optionally a parent_object — a strictly more general "
            "object from THIS SAME LIST that it is a special case of (e.g. 'abelian variety' → "
            "'algebraic variety'), else null.\n\nOBJECTS:\n" + "\n".join(chunk),
            AREA_SCHEMA,
        )
        for a in result["assignments"]:
            t = fold(a["term"])
            if t in chunk:
                area_of[t] = a["area"]
                parent_of[t] = fold(a["parent_object"]) if a["parent_object"] else None

    # ---- resolve + write outputs ----
    def resolve(t):
        seen = set()
        while t in alias_of and alias_of[t] and t not in seen:
            seen.add(t)
            t = alias_of[t]
        return None if (t in alias_of and alias_of[t] is None) else t

    vocab = {}
    final_df = Counter()
    with NORMALIZED.open("w") as f:
        for chash, terms in per_conj.items():
            resolved = sorted({r for t in terms if (r := resolve(t)) and r in set(canonicals)})
            final_df.update(resolved)
            f.write(json.dumps({"content_hash": chash, "objects": resolved}) + "\n")

    # preserve fields added by later stages (03b typing) across rebuilds
    old_vocab = json.loads(VOCAB.read_text()) if VOCAB.exists() else {}

    aliases = defaultdict(list)
    for t, target in alias_of.items():
        if target:
            aliases[resolve(target) or target].append(t)
    for c in canonicals:
        vocab[c] = {
            "aliases": sorted(aliases.get(c, [])),
            "area": area_of.get(c, "other"),
            "parent": parent_of.get(c),
            "df": final_df.get(c, 0),
        }
        for k in ("type", "individual"):
            if c in old_vocab and k in old_vocab[c]:
                vocab[c][k] = old_vocab[c][k]
    VOCAB.write_text(json.dumps(vocab, indent=1))

    # ---- review flags ----
    lines = ["== top 50 canonicals =="]
    for t, c in final_df.most_common(50):
        lines.append(f"{c:5d}  {t}")
    lines.append("\n== mega-merges (>15 aliases) ==")
    for c, al in aliases.items():
        if len(al) > 15:
            lines.append(f"{c}: {len(al)} aliases: {al[:20]}")
    lines.append("\n== near-duplicate canonicals (edit distance <= 2) ==")

    def edit_le2(a, b):
        if abs(len(a) - len(b)) > 2:
            return False
        # cheap DP capped at 2
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            cur = [i]
            for j, cb in enumerate(b, 1):
                cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
            if min(cur) > 2:
                return False
            prev = cur
        return prev[-1] <= 2

    frequent = [t for t, c in final_df.most_common() if c >= 3]
    for i, a in enumerate(frequent):
        for b in frequent[i + 1 :]:
            if edit_le2(a, b):
                lines.append(f"{a}  <->  {b}")
    REVIEW.write_text("\n".join(lines))

    print(f"wrote {VOCAB} ({len(vocab)} objects), {NORMALIZED}, {REVIEW}")
    print("\ntop 20 objects:")
    for t, c in final_df.most_common(20):
        print(f"  {c:4d}  {t}")


if __name__ == "__main__":
    main()
