---
name: prove-conjecture
description: Develop a proof (or a counterexample and a revised statement) for a mathematical conjecture, following the empirically observed practices of research mathematicians. Use when the user asks to prove, attack, explore, or assess a conjecture or open problem.
---

# Prove a conjecture

Work the conjecture the way research mathematicians actually do — alternating **horizontal** work (informal exploration: examples, experiments, reading related proofs) and **vertical** work (formalization: choosing a proof method, chaining known results, generalizing worked cases). The model comes from Fernández-León, Toscano-Barragán & Gavilán-Izquierdo, *How mathematicians conjecture and prove* (CERME10, 2017); their category labels (C.H.a, P.V.d, …) are cited below so the workflow stays traceable to the source. Conjecturing and proving are two sides of one coin: expect to revise the statement while trying to prove it, and to get proof ideas while testing it.

The process is **not linear**. Vertical work spawns new horizontal work (a failed proof step suggests new examples to test; a pattern in examples suggests a lemma). Loop between phases until you reach one of the exit states in Phase 4.

## Phase 0 — Pin down the statement

1. Write the conjecture as a precise conditional: hypotheses ⇒ conclusion. Name every object and quantifier explicitly.
2. Unfold each definition involved. If a term is ambiguous, state the reading you adopt.
3. Record what is already known: proved special cases, known partial results, equivalent formulations. If the conjecture lives in this repo's conjecture map, check the graph data for related statements and references.
4. Identify the extreme/boundary cases of the hypothesis space (the analogue of "Hilbert spaces and R-trees are done; constant curvature is the open middle"). These are where exploration starts.

## Phase 1 — Horizontal exploration

Do these in whatever order the problem invites; interleave freely.

**Detect patterns in concrete objects (C.H.a / P.H.b).** Instantiate the hypotheses with the simplest nontrivial objects and compute. Prefer *executable* experiments — write small Python/SymPy/NumPy scripts, enumerate small cases, plot — over hand calculation when the domain allows it. Look for the property in the conclusion and for *how* it holds: the mechanism observed in an example is often the skeleton of the general proof.

**Stress-test the conjecture (C.H.b).** Actively try to falsify it before investing in a proof. Target the adversarial cases: degenerate objects, boundary parameters, glued/composite constructions, infinite or non-compact variants. A conjecture that survives hostile examples is worth proving; finding a counterexample early is a success, not a failure.

**Harvest techniques from related proofs (P.H.a).** Find proofs of neighboring results (the special cases already proved, analogous theorems in nearby structures) and extract their techniques and tools: what inequality, what construction, what invariant does the work? List each candidate technique with a note on whether its use conditions are met here.

Keep an **evidence log**: every example tested, what was computed, verified/refuted, and any pattern noticed. Inconclusive experiments are informative for direction but are not evidence — say so explicitly.

## Phase 2 — Vertical formalization

**Formalize the pattern (C.V.a).** If exploration revealed a sharper or different regularity than the original statement, state it as a precise lemma or reformulated conjecture before proving anything.

**Select a demonstration method (P.V.a).** Choose deliberately — direct, contraposition, contradiction, induction, case exhaustion, construction — and say why this method fits the statement's logical shape. If the first choice stalls, switching methods is a legitimate move, not a restart.

**Apply harvested techniques (P.V.b) and chain known results (P.V.c).** Build the proof as an explicit chain of implications, citing each known result used with its exact hypotheses. Verify at every link that the hypotheses of the cited result actually hold in your setting — this is where most plausible-looking proofs die.

**Generalize from the worked case (P.V.d).** A powerful and legitimate pattern: write the full proof in a representative concrete case, then show explicitly how each step lifts to the general case. If a step does not lift, that step is the real content of the problem — return to Phase 1 with it.

## Phase 3 — On counterexample: modify, don't abandon

If Phase 1 or 2 produced a counterexample:

1. Diagnose *which* hypothesis the counterexample exploits.
2. Modify the statement (C.H.c): strengthen the hypotheses to exclude the counterexample's mechanism, or weaken the conclusion — choose the smallest modification that the surviving evidence supports.
3. Formalize the revised conjecture (C.V.b) and restart Phase 1 against it. (Anna's example: "every CAT(0) space has (Q4)" died on gluings → revised to "any CAT(0) space with constant curvature satisfies (Q4)", which was then proved.)

## Phase 4 — Exit states and write-up

Stop when you reach one of:

- **Proved.** Deliver the complete proof: statement, method, the chain of lemmas/citations, and the generalization argument if the proof was lifted from a worked case.
- **Refuted.** Deliver the counterexample with full verification, plus the best revised conjecture the evidence supports (or an argument that no natural weakening survives).
- **Partial.** Deliver what is proved (special cases, one implication, conditional results), the precise gap, and the evidence log — stated honestly as partial.

Every write-up must include: the final precise statement, proof status, the evidence log summary, and which steps were machine-checked (scripts run, cases enumerated) versus argued informally. Never present an informal or unverified step as established. If the repo has Lean tooling available and the user wants it, formalizing the final statement (even just the statement, not the proof) is a worthwhile last verification step.

## Anti-patterns

- Attempting a formal proof before any example has been computed (skipping horizontal work).
- Abandoning a conjecture at the first counterexample instead of modifying it.
- Citing a known theorem without checking its hypotheses in the current setting.
- Treating many confirming examples as proof — they only justify the *effort* of proving.
- Hiding inconclusive experiments; log them and what they rule out.
