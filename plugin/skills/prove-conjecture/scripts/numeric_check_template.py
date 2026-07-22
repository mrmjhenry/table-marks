#!/usr/bin/env python3
"""Falsification-script template for Phase 1 (and Phase 4 numeric spot checks).

Copy this into the working directory, fill in the three checks for the claim
at hand, and run it. Keep the filled-in copy — it becomes a regression check
for any later revision of the statement (Phase 3).

The point is executable falsification, not decoration: a claim that survives
a symbolic identity check, a seeded random-instance sweep, and a boundary
sweep has cleared oracle Tier 1. A claim you only checked "in your head" has
not. Seeds are fixed so runs are reproducible and diffable.

Usage:
    python3 numeric_check_template.py          # run all checks
    python3 numeric_check_template.py -v        # verbose (print each instance)

Exit code 0 = no counterexample found under these checks (record which checks).
Exit code 1 = counterexample found (the claim is false as stated — go to Phase 3).
"""

from __future__ import annotations

import argparse
import random
import sys

SEED = 20260718  # fix the seed; change deliberately, never per-run

# Optional heavy deps — import lazily so the template runs even if absent.
try:
    import sympy as sp
except ImportError:
    sp = None


# --------------------------------------------------------------------------
# EDIT THIS: the claim under test, as a Python predicate on a concrete instance.
# Return True if the claim HOLDS for `instance`, False if it FAILS (counterex).
# Example below encodes the toy claim "for integers a,b: (a+b)^2 == a^2+2ab+b^2".
# Replace with the real claim.
# --------------------------------------------------------------------------
def claim_holds(instance: dict) -> bool:
    a, b = instance["a"], instance["b"]
    return (a + b) ** 2 == a * a + 2 * a * b + b * b


def random_instance(rng: random.Random) -> dict:
    """EDIT: draw one random instance of the hypothesis space."""
    return {"a": rng.randint(-1000, 1000), "b": rng.randint(-1000, 1000)}


def boundary_instances() -> list[dict]:
    """EDIT: the degenerate / extreme / boundary cases worth checking explicitly."""
    xs = [0, 1, -1, 2, 10**6, -(10**6)]
    return [{"a": a, "b": b} for a in xs for b in xs]


def symbolic_check() -> tuple[bool, str]:
    """EDIT: a symbolic identity/inequality check via SymPy, if the claim has one.

    Return (passed, message). Return (True, "n/a") if the claim is not
    symbolic. This is the strongest of the three when it applies.
    """
    if sp is None:
        return True, "sympy not available — skipped"
    a, b = sp.symbols("a b")
    lhs = (a + b) ** 2
    rhs = a**2 + 2 * a * b + b**2
    ok = sp.simplify(lhs - rhs) == 0
    return ok, f"simplify(lhs - rhs) == 0 -> {ok}"


# --------------------------------------------------------------------------
# Harness — usually no need to edit below here.
# --------------------------------------------------------------------------
N_RANDOM = 100_000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("-n", "--n-random", type=int, default=N_RANDOM)
    args = ap.parse_args()

    failures: list[dict] = []

    # 1. symbolic identity check
    sym_ok, sym_msg = symbolic_check()
    print(f"[symbolic]  {'PASS' if sym_ok else 'FAIL'}  {sym_msg}")
    if not sym_ok:
        failures.append({"check": "symbolic"})

    # 2. seeded random-instance sweep
    rng = random.Random(SEED)
    rand_fail = 0
    for _ in range(args.n_random):
        inst = random_instance(rng)
        if not claim_holds(inst):
            rand_fail += 1
            failures.append({"check": "random", "instance": inst})
            if args.verbose or rand_fail <= 5:
                print(f"[random]    COUNTEREXAMPLE: {inst}")
            if rand_fail >= 20:
                break
    print(f"[random]    {'PASS' if rand_fail == 0 else 'FAIL'}  "
          f"{args.n_random} instances, seed {SEED}, {rand_fail} failures")

    # 3. boundary / degenerate sweep
    bnd_fail = 0
    for inst in boundary_instances():
        if not claim_holds(inst):
            bnd_fail += 1
            failures.append({"check": "boundary", "instance": inst})
            if args.verbose or bnd_fail <= 5:
                print(f"[boundary]  COUNTEREXAMPLE: {inst}")
    print(f"[boundary]  {'PASS' if bnd_fail == 0 else 'FAIL'}  "
          f"{len(boundary_instances())} cases, {bnd_fail} failures")

    if failures:
        print(f"\nRESULT: counterexample(s) found -> the claim is FALSE as stated. "
              f"Go to Phase 3 (diagnose global/local, then repair).")
        return 1
    print(f"\nRESULT: no counterexample found under "
          f"[symbolic, {args.n_random} random @ seed {SEED}, boundary sweep]. "
          f"Tier-1 cleared; record these checks. (Silent on proof validity.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
