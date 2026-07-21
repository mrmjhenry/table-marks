"""Runtime index over the vendored MSC 2020 taxonomy (vendor/msc2020.json).

The taxonomy is a flat {code: name} dict (6,603 entries); hierarchy is
encoded purely in the key pattern:

    NN-XX   top-level class      ("11-XX"  Number theory)
    NNAxx   subclass             ("11Bxx"  Sequences and sets)
    NNANN   five-character leaf  ("11B25"  Arithmetic progressions)

Used by the proof workspace for field classification (the agent's set_field
tool) and by the knowledge base for its hierarchy walk. Loaded lazily once,
like store.get_graph().
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MSC_PATH = ROOT / "vendor" / "msc2020.json"

_msc: dict[str, str] | None = None


def msc() -> dict[str, str]:
    global _msc
    if _msc is None:
        _msc = json.loads(MSC_PATH.read_text())
    return _msc


def name_of(code: str) -> str | None:
    return msc().get(code)


def validate(codes: list[str]) -> list[str]:
    """Return valid codes; invalid 5-char leaves fall back to their 3-char
    subclass, bare 2-digit classes to NN-XX. Cap 2, order-preserving dedupe.
    (Semantics lifted from scripts/07_msc.py — keep in step with it.)"""
    m = msc()
    out = []
    for c in codes[:2]:
        c = str(c).strip().upper().replace(" ", "")
        if re.fullmatch(r"\d{2}[A-Z]XX", c):     # subclass written any case
            c = c[:3] + "xx"
        if c in m:
            out.append(c)
        elif re.fullmatch(r"\d{2}[A-Z]\d{2}", c) and (c[:3] + "xx") in m:
            out.append(c[:3] + "xx")
        elif re.fullmatch(r"\d{2}", c) and (c + "-XX") in m:
            out.append(c + "-XX")
    return list(dict.fromkeys(out))


def level(code: str) -> str | None:
    """'leaf' | 'subclass' | 'class' | None for a taxonomy key."""
    if re.fullmatch(r"\d{2}-XX", code):
        return "class"
    if re.fullmatch(r"\d{2}[A-Z]xx", code):
        return "subclass"
    if re.fullmatch(r"\d{2}[A-Z]\d{2}", code) or re.fullmatch(r"\d{2}-\d{2}", code):
        return "leaf"
    return None


def parents_of(code: str) -> list[str]:
    """Ancestors, most specific first: '11B25' -> ['11Bxx', '11-XX']."""
    lv = level(code)
    out = []
    if lv == "leaf" and re.fullmatch(r"\d{2}[A-Z]\d{2}", code):
        out = [code[:3] + "xx", code[:2] + "-XX"]
    elif lv == "leaf":                       # NN-NN exposition codes
        out = [code[:2] + "-XX"]
    elif lv == "subclass":
        out = [code[:2] + "-XX"]
    return [c for c in out if c in msc()]


def hierarchy(code: str) -> list[str]:
    """The code plus its ancestors, filtered to real taxonomy keys."""
    return ([code] if code in msc() else []) + parents_of(code)
