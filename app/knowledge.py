"""The field knowledge base: a committed, cross-session store of proof
approaches, techniques, and assumptions, keyed by MSC 2020 field.

Layout: one pretty-printed JSON file per MSC *subclass* under knowledge/
(e.g. knowledge/11Bxx.json holds the subclass and every leaf beneath it;
knowledge/11-XX.json holds class-level entries). Files exist only for
fields that have been encountered. knowledge/README.md documents the
schema for reviewers — the KB is a versioned repo asset, curated via
ordinary git diffs.

Entries carry provenance: origin 'session' (recorded at look-back from an
actual proof, status verified), 'seeded' (agent-recalled playbook material,
status recalled_unverified until checked), or 'theoremsearch' (literature
hits, status cited).

Concurrency: the server is a single process and MCP handlers run
synchronously on the event loop, so read-modify-write never interleaves
in-process; writes are atomic (tmp + os.replace). Across processes the
policy is last-write-wins — acceptable for the single-user localhost
deployment this app targets.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import fields

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = Path(os.environ.get("PROOF_KB_DIR") or ROOT / "knowledge")

KINDS = {"technique", "assumption", "pitfall", "lemma",
         "counterexample_pattern", "literature"}
ORIGINS = {"session", "seeded", "theoremsearch"}
STATUSES = {"verified", "recalled_unverified", "cited"}
DEFAULT_STATUS = {"session": "verified", "seeded": "recalled_unverified",
                  "theoremsearch": "cited"}
_STATUS_RANK = {"verified": 0, "cited": 1, "recalled_unverified": 2}
STATUS_LABEL = {"verified": "verified", "cited": "literature",
                "recalled_unverified": "recalled · unverified"}

# injection caps per hierarchy level: exact code, its subclass, its class
LEVEL_CAPS = (8, 8, 4)
MAX_TOTAL = 20
BODY_TRUNC = 400


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def kb_file_code(code: str) -> str:
    """The file a code's entries live in: leaves file under their subclass;
    subclass and class codes file under themselves."""
    lv = fields.level(code)
    if lv == "leaf" and re.fullmatch(r"\d{2}[A-Z]\d{2}", code):
        return code[:3] + "xx"
    if lv == "leaf":                          # NN-NN exposition leaves
        return code[:2] + "-XX"
    return code


def _path(file_code: str) -> Path:
    return KB_DIR / f"{file_code}.json"


def load_kb(file_code: str) -> dict:
    p = _path(file_code)
    if p.is_file():
        return json.loads(p.read_text())
    return {"code": file_code, "name": fields.name_of(file_code),
            "updated": None, "counters": {"entry": 0}, "entries": []}


def save_kb(kb: dict) -> None:
    kb["updated"] = _now()
    KB_DIR.mkdir(parents=True, exist_ok=True)
    p = _path(kb["code"])
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(kb, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, p)


def _norm_title(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().casefold()


def add_entry(code: str, *, kind: str, title: str, body: str,
              origin: str, session_id: str | None,
              refinement: str | None = None, status: str | None = None,
              entry_id: str | None = None) -> tuple[dict, bool]:
    """Add or refine a KB entry. Returns (entry, created).

    Without entry_id: dedupes on (code, kind, normalized title) — a hit
    returns the existing entry with created=False. With entry_id: updates
    that entry in place (title/body/refinement/status) and appends the
    contributing session id.
    """
    if kind not in KINDS:
        raise ValueError(f"bad kind {kind!r}")
    if origin not in ORIGINS:
        raise ValueError(f"bad origin {origin!r}")
    status = status or DEFAULT_STATUS[origin]
    if status not in STATUSES:
        raise ValueError(f"bad status {status!r}")
    valid = fields.validate([code])
    if not valid:
        raise ValueError(f"unknown MSC code {code!r}")
    code = valid[0]
    kb = load_kb(kb_file_code(code))

    if entry_id:
        e = next((x for x in kb["entries"] if x["id"] == entry_id), None)
        if e is None:
            raise KeyError(f"no entry {entry_id} in {kb['code']}")
        e.update({"title": title, "body": body, "updated": _now()})
        if refinement is not None:
            e["refinement"] = refinement
        e["provenance"]["status"] = status
        if session_id and session_id not in e["provenance"]["session_ids"]:
            e["provenance"]["session_ids"].append(session_id)
        save_kb(kb)
        return e, False

    nt = _norm_title(title)
    dup = next((x for x in kb["entries"]
                if x["code"] == code and x["kind"] == kind
                and _norm_title(x["title"]) == nt), None)
    if dup is not None:
        return dup, False

    kb["counters"]["entry"] += 1
    e = {"id": f"{kb['code']}-k{kb['counters']['entry']:03d}",
         "code": code, "kind": kind, "title": title, "body": body,
         "refinement": refinement,
         "provenance": {"origin": origin,
                        "session_ids": [session_id] if session_id else [],
                        "status": status},
         "created": _now(), "updated": _now()}
    kb["entries"].append(e)
    save_kb(kb)
    return e, True


def get_entry(entry_id: str) -> dict | None:
    file_code = entry_id.rsplit("-k", 1)[0]
    kb = load_kb(file_code)
    return next((e for e in kb["entries"] if e["id"] == entry_id), None)


def _rank(e: dict, refinement: str | None):
    ref_match = 0 if (refinement and e.get("refinement")
                      and refinement.casefold() in e["refinement"].casefold()) else 1
    return (ref_match, _STATUS_RANK.get(e["provenance"]["status"], 9),
            e.get("updated") or "")


def entries_for(code: str, refinement: str | None = None) -> list[dict]:
    """Hierarchy-walked playbook for a code: entries at the exact code, then
    the rest of its subclass, then its class — capped per level and overall."""
    chain = fields.hierarchy(code)
    if not chain:
        return []
    out, seen = [], set()
    for i, c in enumerate(chain):
        kb = load_kb(kb_file_code(c))
        if i == 0 and fields.level(c) == "leaf":
            pool = [e for e in kb["entries"] if e["code"] == c]
        else:   # ancestor position: the *rest* of that file — not the query
                # leaf's own overflow (level caps stay meaningful)
            pool = [e for e in kb["entries"]
                    if e["id"] not in seen and e["code"] != chain[0]]
        pool.sort(key=lambda e: _rank(e, refinement))
        cap = LEVEL_CAPS[min(i, len(LEVEL_CAPS) - 1)]
        for e in pool[:cap]:
            seen.add(e["id"])
            out.append(e)
        if len(out) >= MAX_TOTAL:
            break
    return out[:MAX_TOTAL]


def search(query: str, code: str | None = None,
           kind: str | None = None) -> list[dict]:
    """Token substring match over title/body/refinement; optionally scoped
    to one code's hierarchy or filtered by kind."""
    tokens = [t for t in re.split(r"\W+", query.casefold()) if len(t) > 2]
    files = ([kb_file_code(c) for c in fields.hierarchy(code)] if code
             else [p.stem for p in KB_DIR.glob("*.json")])
    out = []
    for fc in dict.fromkeys(files):
        for e in load_kb(fc)["entries"]:
            if kind and e["kind"] != kind:
                continue
            hay = " ".join([e["title"], e["body"], e.get("refinement") or ""]).casefold()
            if all(t in hay for t in tokens):
                out.append(e)
    out.sort(key=lambda e: _STATUS_RANK.get(e["provenance"]["status"], 9))
    return out[:MAX_TOTAL]


def format_entries(entries: list[dict], heading: str) -> str:
    """Shared formatter for prompt injection and tool results."""
    if not entries:
        return f"{heading}: (empty)"
    lines = [heading]
    for e in entries:
        prov = STATUS_LABEL.get(e["provenance"]["status"], "?")
        ref = f" · {e['refinement']}" if e.get("refinement") else ""
        body = e["body"]
        if len(body) > BODY_TRUNC:
            body = body[:BODY_TRUNC].rstrip() + "…"
        lines.append(f"- [{e['id']}] ({e['kind']} · {e['code']}{ref} · {prov}) "
                     f"**{e['title']}** — {body}")
    return "\n".join(lines)
