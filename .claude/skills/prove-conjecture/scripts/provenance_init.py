#!/usr/bin/env python3
"""Scaffold a PROVENANCE.md for a proof-development session (Phase 5).

The provenance artifact records how a proof was produced so a reader (or a
referee, or future-you) can audit it: what the model did in each phase, which
verification tiers each claim cleared, which errors were found and when, and a
partition of the final text into machine-generated / machine-verified /
human-verified. The credible published LLM-proof papers all ship one; it is
becoming the norm and it is good epistemics regardless.

Usage:
    python3 provenance_init.py "Title of the conjecture" > PROVENANCE.md
    python3 provenance_init.py "Title" --model claude-... --out PROVENANCE.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

TEMPLATE = """# Provenance — {title}

- **Statement (final, precise):** _TODO — fill in the exact statement proved/refuted._
- **Status:** _proved | refuted | partial_
- **Model / version:** {model}
- **Session date:** {date}
- **Highest oracle tier reached (headline claim):** _Tier N — see per-claim table_

## Phase history

| Phase | What was done | Key artifacts (files, scripts) |
|---|---|---|
| 0 — statement + novelty gate | _search terms recorded; claim classified (a) known / (b) plausibly new / (c) open_ | |
| 1 — falsification | _checks run; counterexample search scripts_ | |
| 2 — sketch + lemmas | _named lemmas, locked files_ | |
| 3 — counterexample handling | _Lakatos diagnostics, repairs_ | |
| 4 — verification | _tiers cleared, rounds, errors found_ | |

## Novelty gate

- **Search performed:** _yes/no_ — **terms:** _..._
- **Prior art found:** _none / list_
- **Classification:** _(a) known result to re-derive / (b) plausibly new / (c) open_

## Per-claim verification ledger

| Claim | Oracle tier | Rounds | Errors found & round | Notes |
|---|---|---|---|---|
| Theorem 1 | _Tier _ | | | |
| Lemma 1 | _Tier _ | | | |

Oracle tiers: 0 self-check (conjectural) · 1 executable falsification · 2 independent
LLM re-derivation · 3 cross-model adversarial · 4 machine-checked (Lean/mathlib).

## Errors found and corrected

_Round-by-round log of substantive errors the verification passes caught. Errors
routinely survive to rounds 2+; record which round caught each._

## Citations

| Cited result | Source | Consulted this session? | Hypotheses checked in-setting? |
|---|---|---|---|
| | | _yes / recalled-from-memory_ | _yes/no_ |

_Any row marked recalled-from-memory is `[UNVERIFIED-CITATION]` until confirmed._

## Text partition

_Partition the final write-up: which passages are machine-generated, which were
machine-verified (which tier), which were human-verified. Mark any remaining
`[GAP]` explicitly._

- Machine-generated: _..._
- Machine-verified: _... (tier)_
- Human-verified: _..._
- Open gaps `[GAP]`: _..._
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("title", help="the conjecture / theorem title")
    ap.add_argument("--model", default="_TODO — model id/version_")
    ap.add_argument("--out", default="-", help="output file, or - for stdout")
    args = ap.parse_args()

    text = TEMPLATE.format(title=args.title, model=args.model,
                           date=date.today().isoformat())
    if args.out == "-":
        sys.stdout.write(text)
    else:
        with open(args.out, "w") as f:
            f.write(text)
        print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
