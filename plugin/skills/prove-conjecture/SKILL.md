---
name: prove-conjecture
description: Develop a proof (or a counterexample and a revised statement) for a mathematical conjecture, following the empirically observed practices of research mathematicians. Use when the user asks to prove, attack, explore, or assess a conjecture or open problem.
---

# Prove a conjecture

Work the conjecture the way research mathematicians actually do — alternating **horizontal** work (informal exploration: examples, experiments, reading related proofs) and **vertical** work (formalization: choosing a proof method, chaining known results, generalizing worked cases). The base model is Fernández-León, Toscano-Barragán & Gavilán-Izquierdo (CERME10, 2017; category labels like C.H.a, P.V.d below), extended with Pólya/Newell, Lakatos, Thurston, Gowers' human-oriented theorem proving, and modern AI-prover practice. Sources and evidence for every technique here are in `references/evidence-base.md` alongside this file.

The process is **not linear**. Vertical work spawns new horizontal work (a failed proof step suggests new examples; a pattern in examples suggests a lemma). Loop between phases until you reach an exit state in Phase 4.

**Bundled resources** (load on demand; keep this file as the index):
- `references/evidence-base.md` — the literature and evidence for every technique here.
- `references/verification-protocol.md` — the full Phase 4 verification protocol and oracle hierarchy. Load during verification.
- `references/failure-modes.md` — the documented failure catalog and countermeasures. Load when a proof "feels done."
- `references/lean-bridge.md` — Draft–Sketch–Prove and mathlib guidance. Load only when attempting Tier 4.
- `scripts/numeric_check_template.py` — seeded falsification template (Phase 1 and Phase 4 numeric checks).
- `scripts/provenance_init.py` — scaffolds `PROVENANCE.md` (Phase 5).

## Standing disciplines (apply in every phase)

- **Grade every claim** in your working notes as `verified` / `partially verified` / `unverified`, and label every theorem-level claim with the highest **oracle tier** it cleared (Tier 0 self-check … Tier 4 machine-checked; see Phase 4 and `references/verification-protocol.md`). Verify with *executable scripts* (enumeration, numerical checks) wherever the domain allows, not prose argument. Never build further reasoning on an unverified claim without flagging it. This catches missing-factor-of-two class errors before they propagate.
- **Files are the source of truth, not conversation context.** Over a long session the working state held in context degrades — a lemma's statement blurs, an assumption is silently dropped. Once a lemma passes verification, persist its exact statement and proof to a file and **lock** it: treat it as immutable unless a downstream contradiction forces an explicit reopening. Do not keep anything load-bearing only in memory.
- **Distinguish "I proved" from "I recall."** Any fact, theorem, or citation imported from training memory rather than derived or sourced this session is marked as such. A citation recalled from memory is `[UNVERIFIED-CITATION]` until checked, and is unusable until its hypotheses are confirmed in the current setting. Silent reference fabrication is the single most common documented failure in LLM mathematical writing.
- **Never present a proof with a known gap as complete.** State the gap explicitly with a `[GAP]` marker and what would close it. Inventing a step to satisfy a request for completeness is *pressure-induced confabulation* — the exact failure the verification apparatus exists to catch; do not generate it.
- **Budget effort like the empirical record**: in observed collaborative mathematics, direct proof steps are a minority of productive activity (~a quarter); examples, sub-conjectures, and literature work dominate. If you have spent most of your effort on direct proving and are stuck, that is a signal to return to horizontal work, not to push harder.
- **Every proof step needs a discovery rationale** — a plausible account of how someone could have thought of it from the current problem state ("no rabbits out of hats", Gowers). A step you cannot motivate is a step you cannot trust or generalize; flag it.
- **No brute-force search without a rationale.** Prefer the pruning a human would apply; treat a large feasible case sweep as a design smell unless the problem genuinely is a finite check. Expand definitions lazily — only after checking that no higher-level move applies.
- **Stuck-state playbook.** When a direct proof stalls, the productive moves (per Tao's workflow and the case studies) are: *find a counterexample*, *prove the weakest nontrivial special case*, *identify which hypothesis is doing the work*, *simplify the argument*. Reach for these before pushing harder on the frontal attack.
- **Report calibrated confidence per lemma**, tied to the oracle tier it cleared — never a single global confidence for the whole proof.

## Phase 0 — Pin down the statement, and check prior art

1. Write the conjecture as a precise conditional: hypotheses ⇒ conclusion. Name every object and quantifier explicitly. Ambiguity found here is cheaper than anywhere downstream.
2. Unfold each definition involved. If a term is ambiguous, state the reading you adopt — ambiguous concepts are exactly where counterexamples and monster-barring disputes later arise.
3. Record what is already known: proved special cases, partial results, equivalent formulations. If the `similar_conjectures` / `conjecture_context` tools are available (math-prover plugin), check the OpenConjecture map for related statements, neighbors, and logical relations.
4. **Novelty gate.** Before any proof attempt on a claim presented as new, *search the literature* (web search if available; otherwise flag the novelty as unverified) and **record the search terms used**. AI systems have "solved" problems settled decades earlier under different terminology; the model's training memory is not a reliable index of what is already known. Never assert novelty without a recorded search.
5. **Classify the claim:** (a) a known result to re-derive, (b) plausibly new, (c) open/conjectural. The classification sets the downstream verification burden — a claimed-new result carries the heaviest.
6. Identify the extreme/boundary cases of the hypothesis space. These are where exploration starts.

## Phase 1 — Horizontal exploration

**Counterexample search comes first.** Before any proof attempt, actively try to refute (C.H.b): randomized instances, boundary/degenerate cases, glued or composite constructions, exhaustive enumeration of small instances. A counterexample search fails faster than a proof attempt reveals its obstruction — and a conjecture that *survives* a hostile search usually exposes, in the pattern of near-failures, the structural property that will drive the proof. A proof attempt on a false statement is the most expensive failure and the point of highest confabulation pressure; do not incur it.

Use **executable tools, not mental arithmetic** — seeded SymPy/NumPy/enumeration scripts, saved to the working directory. Start from `scripts/numeric_check_template.py` (symbolic check + seeded random sweep + boundary sweep). Each saved script becomes a regression check for revised statements later. **Gate:** proceed to Phase 2 only after recording either "no counterexample found under checks X, Y, Z" (name them) or a refined statement that survives the checks. Surviving falsification clears **oracle Tier 1** — strong evidence the statement is *true*, but silent on whether any proof of it is *valid*.

Then, interleaving freely:

**Detect patterns in concrete objects (C.H.a / P.H.b).** Instantiate the hypotheses with the simplest nontrivial objects and compute. Prefer executable experiments (Python/SymPy/NumPy, enumeration, plots) over hand calculation. Look for *how* the conclusion holds: the mechanism in an example is often the skeleton of the general proof.

**Harvest from related proofs (P.H.a) — techniques and whole proofs.** Find proofs of neighboring results and extract the techniques that do the work (an inequality, a construction, an invariant), noting whether their use conditions hold here. Also keep the *whole proofs* of the closest results as candidates for transplant-and-repair in Phase 2: an imperfect proof, or a correct proof of a different theorem, is raw material, not junk (Newell).

**Mine the literature for implicit corollaries.** Expert answers routinely extract consequences that are *not explicit* in the cited papers. When reading a related result, ask what it straightforwardly implies for your hypotheses, not just what it states.

Keep an **evidence log**: every example tested, what was computed, verified/refuted, patterns noticed — each entry carrying its claim grade. Inconclusive experiments inform direction but are not evidence; say so explicitly.

## Phase 2 — Vertical formalization

**Decompose before proving (Thurston / Draft-Sketch-Prove).** Draft the informal proof idea first, then turn it into a **proof sketch with named open subgoals** — intermediate lemmas structured so no single step has to hold too much logic at once. Only then work the subgoals. This informal-draft → sketch-with-holes → close-the-holes pipeline measurably beats attacking the target directly.

**Prove lemmas individually and lock them.** Once a lemma passes verification, persist its statement and proof to a file and treat it as immutable unless a downstream contradiction forces reopening (see the files-as-source-of-truth discipline). Prefer *strengthening a known qualitative result into a quantitative one*, or *generalizing a proved special case*, over a frontal assault — this is the pattern behind essentially every published LLM-derived new theorem to date.

**Generate auxiliary problems freely — and integrate them deliberately (Pólya/Newell).** Lemma and related-problem generation is the single most productive move in the heuristic tradition; use it often. But treat integration as its own step: many useful lemmas are *wild* — even once proved, how they serve the main proof is still a problem. After solving any auxiliary problem, explicitly work out its connection back to the target before counting it as progress.

**Transplant and repair (Newell).** Take the closest harvested proof and try to transform it into a proof of the target: substitute objects, patch the steps that break, and treat each break as a named subgoal. This is a distinct move from technique reuse and often faster than forward search.

**Select a demonstration method (P.V.a).** Direct, contraposition, contradiction, induction, case exhaustion, construction — chosen deliberately, with a reason tied to the statement's logical shape. Switching methods after a stall is a legitimate move, not a restart.

**Chain known results (P.V.c).** Build explicit chains of implications, citing each result with its exact hypotheses, and verify at every link that those hypotheses actually hold in your setting — this is where most plausible-looking proofs die. Every citation records its exact statement-as-used, its source, and whether the source was *actually consulted* this session or *recalled from memory* — recalled citations are `[UNVERIFIED-CITATION]` until checked. Do not import a named theorem you have not either sourced or stated precisely enough to check.

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

Verification evidence is only as strong as the **independence** of the verifier from the prover — a verifier that shares the prover's context inherits its blind spots. Run all of the following; they do not substitute for each other. **Load `references/verification-protocol.md` for the full protocol and the oracle hierarchy.**

Content checks — *what* to look for:

1. **Idea-level weakness hunt (Thurston).** Adversarially search the proof's *ideas* for weaknesses: which step would an expert distrust, where is the argument thinnest, what is the most suspicious inequality or limit exchange? Humans (and models) are better at this than at line-by-line checking, and it catches different errors.
2. **Step-level checks — not holistic review.** Verify each inference *exactly as stated*; process-level checking beats "the proof looks correct overall" (Lightman et al.). *Instantiate individual steps on concrete examples* (Weber & Mejia-Ramos) — trace a specific object through end to end. Every sub-argument must end by establishing exactly the goal it opened with (Lamport); a proof that ends somewhere adjacent to its goal is a classic hidden failure.
3. **Test against independent information (Thurston).** Check the theorem's consequences against everything independently known: known special cases, asymptotics, numerical data, dualities. A proved statement that contradicts independent knowledge means the proof is wrong somewhere.
4. **Numeric spot checks on the final proof.** Re-run Phase-1-style scripts against every quantitative claim that survives into the final argument (constants, exponents, inequality directions, factor-of-two coefficients) — the most common surviving defect class. Use `scripts/numeric_check_template.py`.

Independence checks — *who* looks and *how independently*:

5. **Independent re-derivation.** Spawn a fresh pass (subagent or new session) that receives **only the statement and the candidate proof** — never the derivation history, scratch work, or your stated confidence. Instruct it to hunt for errors, not confirm.
6. **Adversarial rounds.** Run the independent audit for multiple rounds (default 3; more for a headline claim), fixing errors and re-auditing from scratch between rounds — substantive errors routinely survive to rounds 2+. Use a second model family for a round when available.

**Oracle tier.** Grade the result by the highest tier it cleared and label it as such: Tier 0 self-check (conjectural) · 1 executable falsification · 2 independent LLM re-derivation · 3 cross-model adversarial · 4 machine-checked (Lean/mathlib — see `references/lean-bridge.md`). Reach for Tier 4 on discrete/algebraic/combinatorial claims; don't force it on hard analysis. A claim that cleared only Tier 0 is conjectural, not proved.

Then **look back (Pólya / Lakatos)**:

- **Proof-generated concepts:** compare what the proof actually required against the concepts in the statement. If the proof's real working conditions define a sharper concept (the uniform-convergence pattern), propose the redefinition and the correspondingly reshaped theorem.
- What generalizes? Which lemmas are reusable beyond this problem? Log them. If `query_knowledge`/`record_knowledge` tools are available, make the log durable: query first, then record what this session actually established (`origin='session'`), refining existing entries via `entry_id` rather than duplicating.

Exit states:

- **Proved.** Deliver the complete proof: statement, method, sketch structure with all subgoals closed, the chain of citations with hypothesis checks, the generalization argument if lifted from a worked case, and the verification passes above with the oracle tier reached.
- **Refuted.** Deliver the counterexample with executable verification, the Lakatos diagnostic, plus the best revised conjecture the evidence supports (or an argument that no natural repair survives).
- **Partial.** Deliver what is proved (special cases, one implication, conditional results), the precise gap as a named open subgoal (`[GAP]`), and the graded evidence log — stated honestly as partial.

Every write-up must include: the final precise statement, proof status, the evidence log summary with per-claim grades **and oracle tiers**, the novelty-gate result (search terms + classification), citations marked consulted-vs-recalled, and a partition of the text into machine-generated / machine-verified / human-verified. Never present an unverified step as established, and never present a `[GAP]` as closed.

## Phase 5 — Provenance log

Emit a provenance artifact alongside the proof — scaffold it with `scripts/provenance_init.py` (`python3 provenance_init.py "<title>" --out PROVENANCE.md`). It records: model/version, phase history, the novelty-gate search, the per-claim verification ledger (tier reached, rounds, errors found and in which round), citations with consulted-vs-recalled status, and the machine-generated / machine-verified / human-verified partition of the final text. The credible published LLM-proof papers all ship one; it is becoming the publication norm and it is good epistemics regardless of publication.

## Situational extensions

Use when the setting supports them; skip otherwise.

- **Learnability gate (Davies et al., Nature 2021).** When the conjecture asserts a relationship X→Y over a family of objects you can generate in bulk, train a simple model to predict Y from X before investing proof effort: above-chance accuracy confirms a real relationship, and feature attribution tells you *which* variables to build the proof around.
- **Numerics-first conjecture mining (Ramanujan Machine).** For identity-shaped questions, enumerate candidate expressions and match numerically to high precision before any proof work; rediscovered known identities validate the search.
- **Lemma library (LEGO-Prover).** Across a longer campaign, accumulate proved lemmas as reusable assets and record failed lemma statements as open requests; check the library before proving anything from scratch.
- **Tractability triage.** With many candidate conjectures or subgoals, estimate which are most likely closable and spend budget there first.
- **Formalization discipline (oracle Tier 4).** If formalizing (e.g., Lean), use Draft–Sketch–Prove and the disciplines in `references/lean-bridge.md`: type-checking is not semantic faithfulness — separately check the formal statement says what the informal one means; try proving the *negation* as a falsification filter; reject `sorry` as an escape hatch; maintain a Blueprint dependency graph for large developments. If the math-prover plugin is loaded, its `lean_check` tool compiles against a pinned Mathlib and the `lean-formalizer` agent runs the compile-fix loop — use them rather than re-inventing one.

## Anti-patterns

- Attempting a formal proof before any example has been computed, or before a counterexample search has run.
- Asserting a claim is new without a recorded literature search (novelty gate skipped).
- "Verifying" a proof by re-reading it and finding it convincing — wishful verification. Or verifying with full access to the prover's own reasoning — circular verification. Independence is the whole point.
- Stopping verification at the first clean-looking round; substantive errors routinely survive to rounds 2+.
- Citing a result recalled from memory without marking it `[UNVERIFIED-CITATION]` and checking its hypotheses. Fabricated citations are the most common LLM-math failure.
- Presenting a proof with a known gap as complete, or inventing a step under pressure to look finished, instead of marking `[GAP]`.
- Emitting a theorem without an oracle-tier label, or labeling single-family clean-context review as Tier 3.
- Treating a Lean compile as semantic faithfulness, or leaving a `sorry` and calling the proof closed.
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
