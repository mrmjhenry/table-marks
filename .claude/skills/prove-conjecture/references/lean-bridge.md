# Tier 4: the Lean / mathlib bridge (Draft–Sketch–Prove)

Load this only when attempting **oracle Tier 4** — machine-checked formalization. Machine checking is the only *hard* oracle available, but it is not free and not always appropriate. Read the tractability call first.

## When to reach for Tier 4 — and when not to

**Reach for it** when the claim is combinatorial, algebraic, number-theoretic, order-theoretic, or otherwise discrete, and the objects have plausible mathlib coverage (finite sets, integers, polynomials, groups, basic real analysis). These are where formalization is tractable and where a compiled proof settles the matter.

**Do not force it** where the mathematics makes it impractical: much of hard analysis, anything leaning on large unformalized theories, or a claim whose informal proof depends on machinery mathlib lacks. A Tier-2/3 analysis proof, honestly labeled, beats a Lean file padded with `sorry`. Forcing Lean where it does not fit produces a fake hard-oracle result — worse than an honest soft-oracle one.

## The Draft–Sketch–Prove procedure (arXiv:2210.12283)

Do not translate a finished informal proof line-by-line into tactics — that fails on the first construct mathlib names differently. Instead:

1. **Draft** — the informal proof, already in hand from Phase 2/3.
2. **Sketch** — a formal skeleton in Lean that mirrors the informal steps: the theorem statement, the intermediate lemmas as `have` steps with their types, and `sorry` in each proof obligation. This is the informal structure made formal, with the holes still open. Getting the *statement* and the *decomposition* to typecheck is most of the work.
3. **Prove** — close each `sorry`, innermost/easiest first, with tactics (`simp`, `omega`, `ring`, `linarith`, `exact?`, library lemmas). Run the compiler, read the error, repair, repeat. A single hard obligation that will not close is a real subgoal — surface it as a `[GAP]`, do not paper it with `sorry` and call the proof done.

## Two disciplines that matter more than the tactics

- **Type-checking is not semantic faithfulness.** A Lean file can compile while proving *the wrong statement* — a mis-stated hypothesis, a wrong quantifier order, `ℕ` where `ℤ` was meant, natural-number subtraction/division truncating silently, a vacuous premise. **Separately** check that the formal statement says what the informal one means: compare quantifiers and hypotheses one by one, and confirm no premise is trivially unsatisfiable. This check is not optional and is not implied by a green compile.
- **Try proving the negation as a falsification filter.** Before or alongside proving the statement, attempt to prove its negation in Lean. If the negation closes easily, the formal statement is wrong (usually vacuous or mis-quantified), not the mathematics. Cheap, and it catches faithfulness bugs a passing compile hides.

## Large developments: Blueprint structure

For a multi-lemma campaign, maintain a Blueprint-style dependency graph (Tao's PFR / Equational Theories pattern): a human-readable proof document linked to the Lean, auto-generating a lemma dependency graph color-coded by formalization status (stated / proved-informally / formalized / compiled). It tells you the next actionable node and keeps the informal and formal proofs in correspondence. Reject any proof containing `sorry` as an escape hatch (LEGO-Prover discipline) — a `sorry` is an open subgoal, tracked as such, never a closed one.

## In this repo's proof workspace

The workspace (`app/`) already implements this bridge operationally: the `lean-formalizer` subagent runs the compile-fix loop against a pinned mathlib, and `app/lean.py` is the deterministic checker. The main agent must review statement-faithfulness before a step earns its machine-checked badge — that is the "type-checking is not faithfulness" discipline above, enforced in code. When running here, use that machinery rather than re-inventing a compile loop.
