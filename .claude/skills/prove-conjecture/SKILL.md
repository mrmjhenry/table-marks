---
name: prove-conjecture
description: Develop a proof (or a counterexample and a revised statement) for a mathematical conjecture, following the empirically observed practices of research mathematicians. Use when the user asks to prove, attack, explore, or assess a conjecture or open problem.
---

# Prove a conjecture

Work the conjecture the way research mathematicians actually do — alternating **horizontal** work (informal exploration: examples, experiments, reading related proofs) and **vertical** work (formalization: choosing a proof method, chaining known results, generalizing worked cases). The base model is Fernández-León, Toscano-Barragán & Gavilán-Izquierdo (CERME10, 2017; category labels like C.H.a, P.V.d below), extended with Pólya/Newell, Lakatos, Thurston, Gowers' human-oriented theorem proving, and modern AI-prover practice. Sources and evidence for every technique here are in `references.md` alongside this file.

The process is **not linear**. Vertical work spawns new horizontal work (a failed proof step suggests new examples; a pattern in examples suggests a lemma). Loop between phases until you reach an exit state in Phase 4.

## Standing disciplines (apply in every phase)

- **Grade every claim** in your working notes as `verified` / `partially verified` / `unverified`. Verify with *executable scripts* (enumeration, numerical checks) wherever the domain allows, not prose argument. Never build further reasoning on an unverified claim without flagging it. This discipline catches missing-factor-of-two class errors before they propagate.
- **Budget effort like the empirical record**: in observed collaborative mathematics, direct proof steps are a minority of productive activity (~a quarter); examples, sub-conjectures, and literature work dominate. If you have spent most of your effort on direct proving and are stuck, that is a signal to return to horizontal work, not to push harder.
- **Every proof step needs a discovery rationale** — a plausible account of how someone could have thought of it from the current problem state ("no rabbits out of hats", Gowers). A step you cannot motivate is a step you cannot trust or generalize; flag it.
- **No brute-force search without a rationale.** Prefer the pruning a human would apply; treat a large feasible case sweep as a design smell unless the problem genuinely is a finite check. Expand definitions lazily — only after checking that no higher-level move applies.

## Phase 0 — Pin down the statement

1. Write the conjecture as a precise conditional: hypotheses ⇒ conclusion. Name every object and quantifier explicitly.
2. Unfold each definition involved. If a term is ambiguous, state the reading you adopt — ambiguous concepts are exactly where counterexamples and monster-barring disputes later arise.
3. Record what is already known: proved special cases, partial results, equivalent formulations. If the conjecture lives in this repo's conjecture map, check the graph data for related statements and references.
4. Identify the extreme/boundary cases of the hypothesis space. These are where exploration starts.

## Phase 1 — Horizontal exploration

**Counterexample search comes first.** Before any proof attempt, actively try to refute (C.H.b): randomized instances, boundary/degenerate cases, glued or composite constructions, exhaustive enumeration of small instances. A counterexample search fails faster than a proof attempt reveals its obstruction — and a conjecture that *survives* a hostile search usually exposes, in the pattern of near-failures, the structural property that will drive the proof. Write the search as a script where possible and keep it; it becomes a regression check for revised statements later.

Then, interleaving freely:

**Detect patterns in concrete objects (C.H.a / P.H.b).** Instantiate the hypotheses with the simplest nontrivial objects and compute. Prefer executable experiments (Python/SymPy/NumPy, enumeration, plots) over hand calculation. Look for *how* the conclusion holds: the mechanism in an example is often the skeleton of the general proof.

**Harvest from related proofs (P.H.a) — techniques and whole proofs.** Find proofs of neighboring results and extract the techniques that do the work (an inequality, a construction, an invariant), noting whether their use conditions hold here. Also keep the *whole proofs* of the closest results as candidates for transplant-and-repair in Phase 2: an imperfect proof, or a correct proof of a different theorem, is raw material, not junk (Newell).

**Mine the literature for implicit corollaries.** Expert answers routinely extract consequences that are *not explicit* in the cited papers. When reading a related result, ask what it straightforwardly implies for your hypotheses, not just what it states.

Keep an **evidence log**: every example tested, what was computed, verified/refuted, patterns noticed — each entry carrying its claim grade. Inconclusive experiments inform direction but are not evidence; say so explicitly.

## Phase 2 — Vertical formalization

**Decompose before proving (Thurston / Draft-Sketch-Prove).** Draft the informal proof idea first, then turn it into a **proof sketch with named open subgoals** — intermediate lemmas structured so no single step has to hold too much logic at once. Only then work the subgoals. This informal-draft → sketch-with-holes → close-the-holes pipeline measurably beats attacking the target directly.

**Generate auxiliary problems freely — and integrate them deliberately (Pólya/Newell).** Lemma and related-problem generation is the single most productive move in the heuristic tradition; use it often. But treat integration as its own step: many useful lemmas are *wild* — even once proved, how they serve the main proof is still a problem. After solving any auxiliary problem, explicitly work out its connection back to the target before counting it as progress.

**Transplant and repair (Newell).** Take the closest harvested proof and try to transform it into a proof of the target: substitute objects, patch the steps that break, and treat each break as a named subgoal. This is a distinct move from technique reuse and often faster than forward search.

**Select a demonstration method (P.V.a).** Direct, contraposition, contradiction, induction, case exhaustion, construction — chosen deliberately, with a reason tied to the statement's logical shape. Switching methods after a stall is a legitimate move, not a restart.

**Chain known results (P.V.c).** Build explicit chains of implications, citing each result with its exact hypotheses, and verify at every link that those hypotheses actually hold in your setting — this is where most plausible-looking proofs die.

**Generalize from the worked case (P.V.d).** Write the full proof in a representative concrete case, then show how each step lifts to the general case. A step that does not lift is the real content of the problem — return to Phase 1 with it.

## Phase 3 — Counterexample handling: diagnose, then branch

When a counterexample appears (in Phase 1 against the conjecture, or in Phase 2 against a proof step), do not jump straight to weakening the statement. First run the **Lakatos diagnostic** — two independent questions:

- Does it refute the **conjecture itself** (global)?
- Does it refute a **specific step/lemma of the current proof attempt** (local)?

Route by the answer:

- **Local but not global** — the conjecture survives; a proof step is wrong. Repair or replace that step; the statement needs no change.
- **Global and local** — the guilty proof step is identified. Prefer **lemma-incorporation**: build that step's condition into the theorem's hypotheses, turning the failed proof into a proof of the corrected statement.
- **Global but not local** — the proof "succeeds" on a false statement, so a **hidden lemma** is being used silently. Make the implicit assumptions explicit as proof steps, then re-run the diagnostic and lemma-incorporate.

When modifying the statement, choose among the named repair operations, in roughly this order of preference:

1. **Lemma-incorporation** — add the condition the proof actually needs (keeps statement and proof coupled; Lakatos's preferred method).
2. **Exception-barring / strategic withdrawal** — restrict to a safe domain or list explicit exceptions, guided by which hypothesis the counterexample exploits; keep the restriction as small as the surviving evidence supports.
3. **Monster-barring / monster-adjustment** — argue the "counterexample" isn't a legitimate instance by sharpening an ambiguous definition (or reinterpreting the object). Legitimate when the concept genuinely was ambiguous (Phase 0 step 2); dishonest when used to dodge a fair refutation — always flag a definition change explicitly as such.
4. **Surrender** — abandon the conjecture only when no natural repair survives the evidence; record why.

Formalize the revised statement (C.V.b) and restart Phase 1 against it — beginning with the saved counterexample-search scripts as a regression check.

## Phase 4 — Verification, look-back, and write-up

Before claiming any exit state, run three distinct checks — they do not substitute for each other:

1. **Idea-level weakness hunt (Thurston).** Adversarially search the proof's *ideas* for weaknesses: which step would an expert distrust, where is the argument thinnest, what is the most suspicious inequality or limit exchange? Humans (and models) are better at this than at line-by-line checking, and it catches different errors.
2. **Step-level checks.** Verify each step formally, and *instantiate individual steps on concrete examples* (Weber & Mejia-Ramos) — trace a specific object through the argument end to end. Every sub-argument must end by establishing exactly the goal it opened with (Lamport); a proof that ends somewhere adjacent to its goal is a classic hidden failure.
3. **Test against independent information (Thurston).** Check the theorem's consequences against everything independently known: known special cases, asymptotics, numerical data, dualities. A proved statement that contradicts independent knowledge means the proof is wrong somewhere.

Then **look back (Pólya / Lakatos)**:

- **Proof-generated concepts:** compare what the proof actually required against the concepts in the statement. If the proof's real working conditions define a sharper concept (the uniform-convergence pattern), propose the redefinition and the correspondingly reshaped theorem.
- What generalizes? Which lemmas are reusable beyond this problem? Log them.

Exit states:

- **Proved.** Deliver the complete proof: statement, method, sketch structure with all subgoals closed, the chain of citations with hypothesis checks, the generalization argument if lifted from a worked case, and the three verification passes above.
- **Refuted.** Deliver the counterexample with executable verification, the Lakatos diagnostic, plus the best revised conjecture the evidence supports (or an argument that no natural repair survives).
- **Partial.** Deliver what is proved (special cases, one implication, conditional results), the precise gap as a named open subgoal, and the graded evidence log — stated honestly as partial.

Every write-up must include: the final precise statement, proof status, the evidence log summary with claim grades, and which steps were machine-checked versus argued informally. Never present an unverified step as established.

## Situational extensions

Use when the setting supports them; skip otherwise.

- **Learnability gate (Davies et al., Nature 2021).** When the conjecture asserts a relationship X→Y over a family of objects you can generate in bulk, train a simple model to predict Y from X before investing proof effort: above-chance accuracy confirms a real relationship, and feature attribution tells you *which* variables to build the proof around.
- **Numerics-first conjecture mining (Ramanujan Machine).** For identity-shaped questions, enumerate candidate expressions and match numerically to high precision before any proof work; rediscovered known identities validate the search.
- **Lemma library (LEGO-Prover).** Across a longer campaign, accumulate proved lemmas as reusable assets and record failed lemma statements as open requests; check the library before proving anything from scratch.
- **Tractability triage.** With many candidate conjectures or subgoals, estimate which are most likely closable and spend budget there first.
- **Formalization discipline.** If formalizing (e.g., Lean): type-checking is not semantic faithfulness — separately check the formal statement says what the informal one means; and try proving the *negation* as a falsification filter. For large developments, maintain a Blueprint-style dependency graph of lemmas with formalization status.

## Anti-patterns

- Attempting a formal proof before any example has been computed, or before a counterexample search has run.
- Treating a counterexample as one undifferentiated event instead of running the global/local diagnostic.
- Abandoning a conjecture at the first counterexample instead of branching over the repair operations.
- Silently redefining a concept to dodge a counterexample (monster-barring without flagging it).
- Citing a known theorem without checking its hypotheses in the current setting.
- Building further argument on a claim never graded or verified.
- Emitting a proof step with no discovery rationale — if it looks like a rabbit from a hat, it is unmotivated and untrustworthy.
- Counting a solved lemma as progress before working out how it integrates into the main proof.
- Expanding definitions eagerly when a higher-level move is available.
- Treating many confirming examples as proof — they only justify the *effort* of proving.
- Hiding inconclusive experiments; log them and what they rule out.
- A sub-proof that ends on a statement adjacent to, but not identical with, its stated goal.
