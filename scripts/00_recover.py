#!/usr/bin/env python3
"""Stage 0 (optional): Recover withheld conjecture text from arXiv e-prints.

The dataset withholds text for rows whose papers are under arXiv's
non-exclusive-distribution license, but records the exact provenance:
source_url (e-print archive), source_file, start_line, end_line.
This stage downloads each e-print (rate-limited, cached), reads the recorded
line span, and writes data/recovered.jsonl keyed by the dataset row id.

LICENSING: recovered text is for LOCAL RESEARCH USE ONLY and must not be
republished — data/ is gitignored and 04_graph.py excludes recovered text
from the publishable map by default.
"""
import gzip
import io
import json
import tarfile
import time
import urllib.request
from pathlib import Path

from datasets import load_dataset

ROOT = Path(__file__).resolve().parent.parent
EPRINTS = ROOT / "data" / "eprints"
OUT = ROOT / "data" / "recovered.jsonl"
FAIL = ROOT / "data" / "recover_failures.jsonl"

DELAY_S = 3.0
UA = "openconjecture-map/1.0 (personal research; contact: https://github.com/mrmjhenry/explore-open-conjectures)"


def fetch_eprint(arxiv_id: str, url: str) -> Path | None:
    dest = EPRINTS / f"{arxiv_id}.bin"
    if dest.exists():
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            dest.write_bytes(r.read())
        time.sleep(DELAY_S)
        return dest
    except Exception as e:
        print(f"  download failed {arxiv_id}: {e}")
        time.sleep(DELAY_S)
        return None


def read_source_file(blob: bytes, source_file: str) -> list[str] | None:
    """E-prints are tar.gz archives, single gzipped files, or raw files."""
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tf:
            names = tf.getnames()
            match = next((n for n in names if n == source_file), None) \
                or next((n for n in names if n.endswith("/" + source_file)), None) \
                or next((n for n in names if Path(n).name == Path(source_file).name), None)
            if not match:
                return None
            data = tf.extractfile(match).read()
            return data.decode("utf-8", errors="replace").splitlines()
    except tarfile.TarError:
        pass
    try:
        text = gzip.decompress(blob).decode("utf-8", errors="replace")
        return text.splitlines()
    except Exception:
        pass
    if blob[:5] != b"%PDF-":
        try:
            return blob.decode("utf-8", errors="replace").splitlines()
        except Exception:
            pass
    return None


def main():
    EPRINTS.mkdir(parents=True, exist_ok=True)
    ds = load_dataset("davisrbr/openconjecture", "conjectures", split="train")
    df = ds.to_pandas()
    w = df[df.text_withheld][["id", "arxiv_id", "source_url", "source_file",
                              "start_line", "end_line"]]

    done = set()
    if OUT.exists():
        done = {json.loads(l)["id"] for l in OUT.read_text().splitlines() if l.strip()}
    failed = set()
    if FAIL.exists():
        failed = {json.loads(l)["id"] for l in FAIL.read_text().splitlines() if l.strip()}
    pending = w[~w["id"].isin(done | failed)]
    print(f"{len(w)} withheld rows, {len(done)} recovered, {len(failed)} failed, {len(pending)} pending "
          f"({pending.arxiv_id.nunique()} papers to fetch)")

    blob_cache = {}
    n_ok = n_fail = 0
    for row in pending.itertuples():
        if row.arxiv_id not in blob_cache:
            p = fetch_eprint(row.arxiv_id, row.source_url)
            blob_cache[row.arxiv_id] = p.read_bytes() if p else None
            if len(blob_cache) % 25 == 0:
                print(f"  …{len(blob_cache)} papers fetched, {n_ok} rows recovered")
        blob = blob_cache[row.arxiv_id]
        rec = None
        if blob is not None:
            lines = read_source_file(blob, row.source_file)
            if lines and 1 <= row.start_line <= len(lines):
                body = "\n".join(lines[row.start_line - 1 : min(row.end_line, len(lines))])
                if body.strip():
                    rec = {"id": int(row.id), "arxiv_id": row.arxiv_id, "body_tex": body}
        if rec:
            with OUT.open("a") as f:
                f.write(json.dumps(rec) + "\n")
            n_ok += 1
        else:
            with FAIL.open("a") as f:
                f.write(json.dumps({"id": int(row.id), "arxiv_id": row.arxiv_id}) + "\n")
            n_fail += 1

    print(f"recovered {n_ok}, failed {n_fail}; total now {len(done) + n_ok}/{len(w)}")


if __name__ == "__main__":
    main()
