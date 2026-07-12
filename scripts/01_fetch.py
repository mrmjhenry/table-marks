#!/usr/bin/env python3
"""Stage 1: Fetch openconjecture, filter to public-text rows, clean LaTeX, dedupe.

Output: data/conjectures.parquet — one row per distinct conjecture (content_hash),
with model_text (for LLM extraction) and display_text (for the visualization).
"""
import hashlib
import json
import re
from pathlib import Path

import pandas as pd
from datasets import load_dataset

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "conjectures.parquet"
RECOVERED = ROOT / "data" / "recovered.jsonl"  # optional, from 00_recover.py

MODEL_TEXT_MAX_CHARS = 6000
DISPLAY_TEXT_MAX_CHARS = 4000
RENDER_TEX_MAX_CHARS = 4000


def clean_latex(tex: str) -> str:
    """Light cleaning for display/model text; keeps $...$ math verbatim."""
    s = tex
    s = re.sub(r"(?<!\\)%.*", "", s)  # TeX comments
    s = re.sub(r"\\label\{[^}]*\}", "", s)
    s = re.sub(r"\\(?:cite|citep|citet|cref|Cref|ref|eqref)\*?(?:\[[^\]]*\])?\{[^}]*\}", "[ref]", s)
    s = re.sub(r"\\(?:begin|end)\{[^}]*\}", " ", s)
    s = re.sub(r"\\(?:textup|textrm|textit|textbf|emph|mbox|text)\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\(?:medskip|smallskip|bigskip|noindent|par)\b", " ", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def clean_for_render(tex: str) -> str:
    """Gentle cleaning for KaTeX rendering — keeps $…$ and math environments."""
    s = re.sub(r"(?<!\\)%.*", "", tex)
    s = re.sub(r"\\label\{[^}]*\}", "", s)
    s = re.sub(r"\\(?:cite|citep|citet|cref|Cref|ref|eqref)\*?(?:\[[^\]]*\])?\{[^}]*\}", "[ref]", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def norm_for_hash(title: str, text: str) -> str:
    s = (title + " " + text).lower()
    s = re.sub(r"(?<!\\)%.*", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def main():
    ds = load_dataset("davisrbr/openconjecture", "conjectures", split="train")
    df = ds.to_pandas()
    n0 = len(df)

    # merge recovered withheld text (local research use only — see 00_recover.py)
    df["text_source"] = "dataset"
    n_rec = 0
    if RECOVERED.exists():
        rec = {json.loads(l)["id"]: json.loads(l)["body_tex"]
               for l in RECOVERED.read_text().splitlines() if l.strip()}
        mask = df["id"].isin(rec) & df["text_withheld"]
        df.loc[mask, "body_tex"] = df.loc[mask, "id"].map(rec)
        df.loc[mask, "plain_text"] = ""
        df.loc[mask, "text_withheld"] = False
        df.loc[mask, "text_source"] = "recovered"
        n_rec = int(mask.sum())

    df = df[~df["text_withheld"]].copy()
    n1 = len(df)

    # Text: prefer plain_text, fall back to cleaned body_tex
    df["display_text"] = [
        (pt if isinstance(pt, str) and pt.strip() else clean_latex(bt or ""))
        for pt, bt in zip(df["plain_text"], df["body_tex"])
    ]
    df = df[df["display_text"].str.strip().astype(bool)].copy()
    n2 = len(df)

    df["model_text"] = df["display_text"].str.slice(0, MODEL_TEXT_MAX_CHARS)
    df["display_text"] = df["display_text"].str.slice(0, DISPLAY_TEXT_MAX_CHARS)

    # For KaTeX rendering: prefer gently-cleaned body_tex (math intact).
    # Does NOT feed the content hash — extraction cache keys stay stable.
    df["render_tex"] = [
        clean_for_render(bt)[:RENDER_TEX_MAX_CHARS]
        if isinstance(bt, str) and bt.strip() else ""
        for bt in df["body_tex"]
    ]

    # Dedupe restated conjectures across papers by normalized title+text hash
    df["chash"] = [
        hashlib.sha256(norm_for_hash(t, x).encode()).hexdigest()[:16]
        for t, x in zip(df["title"], df["display_text"])
    ]
    # Also collapse identical statements with different titles (same conjecture restated):
    # use text-only hash as the dedupe key when the statement is substantial.
    df["thash"] = [
        hashlib.sha256(re.sub(r"\s+", " ", x.lower()).strip().encode()).hexdigest()[:16]
        for x in df["display_text"]
    ]
    dupes = df["thash"].duplicated().sum()

    agg_ids = df.groupby("thash")["arxiv_id"].agg(lambda s: sorted(set(s))).rename("all_arxiv_ids")
    df = df.sort_values("published_at").drop_duplicates("thash", keep="first")
    df = df.merge(agg_ids, on="thash")
    n3 = len(df)

    keep = df[[
        "thash", "arxiv_id", "all_arxiv_ids", "title", "authors", "primary_category",
        "categories", "published_at", "abs_url", "latest_label",
        "latest_interestingness_score", "latest_viability_score",
        "model_text", "display_text", "render_tex", "text_source",
    ]].rename(columns={"thash": "content_hash"})

    OUT.parent.mkdir(exist_ok=True)
    keep.to_parquet(OUT, index=False)

    print(f"total rows:            {n0}")
    print(f"recovered text merged: {n_rec}")
    print(f"with text:             {n1}")
    print(f"non-empty text:        {n2}")
    print(f"after dedupe:          {n3}  (collapsed {dupes} restatements)")
    print(f"open conjectures:      {(keep['latest_label'] == 'real_open_conjecture').sum()}")
    print(f"wrote {OUT}")
    print("\n--- samples ---")
    for _, r in keep.sample(5, random_state=7).iterrows():
        print(f"\n[{r['primary_category']}] {r['title'][:80]}\n  {r['display_text'][:200]}")


if __name__ == "__main__":
    main()
