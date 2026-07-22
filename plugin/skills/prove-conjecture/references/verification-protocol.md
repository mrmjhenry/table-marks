# Verification protocol and oracle hierarchy

Load this during **Phase 4** (verification), or whenever a claim is about to be labeled as established. It expands the Phase 4 summary in SKILL.md. Evidence for each requirement is in `evidence-base.md` §6, §7, §10.

**Design principle: anti-circularity.** A verifier that shares the prover's derivation context inherits the prover's blind spots. Verification evidence is only as strong as the *independence* of the verifier from the thing being verified. Every rule below exists to buy independence.

---

## The protocol (five checks)

Run these in addition to the three Phase-4 checks already in SKILL.md (idea-level weakness hunt, step-level checks, test-against-independent-information). Those establish *what* to look for; this establishes *who* looks and *how independently*.

1. **Step-level audit, not holistic review.** Walk the proof inference by inference. For each step ask: "does this follow from what precedes it, *exactly as stated*?" Process-level checking materially outperforms outcome-level checking (Lightman et al. 2305.20050). A verdict of "the proof looks correct overall" is not acceptable output — it is the absence of verification wearing its costume.

2. **Independent re-derivation.** Spawn a fresh verification pass — a subagent or a new session — that receives **only the theorem statement and the candidate proof**. It must NOT see the derivation history, the scratch work, the discarded attempts, or the prover's stated confidence. Instruct it to actively hunt for errors, not to confirm the result. The clean context is the entire point; leaking the prover's reasoning defeats it.

3. **Adversarial rounds.** Run the independent audit for multiple rounds — default **3**, more for a headline claim. Between rounds, fix the errors found and then **re-audit from scratch** (a fresh clean-context pass, not a patch review of the diff). Empirical basis: in the published Kochen–Specker workflow (2603.16988), adversarial review found substantive errors in **rounds 2 and 5** — errors routinely survive early rounds. Stop when a full round finds nothing, not at the first clean-looking pass.
   - If a **second model family** is available, use it for at least one round (this is Tier 3; see below).
   - If not, maximize independence another way: clean context, an explicitly adversarial system framing ("your job is to find the fatal flaw; assume one exists"), and separation in time/among passes. Single-family clean-context review is Tier 2 — real, but weaker against shared blind spots. Do not label it Tier 3.

4. **Numeric spot checks on the final proof.** Re-run Phase-1-style executable checks against every *quantitative* claim that survives into the final argument: constants, exponents, inequality directions, factor-of-two coefficients, limit/sum exchanges. Inequality-direction and constant-tracking errors are the most common surviving defect class (FirstProof, 2602.05192). Use `scripts/numeric_check_template.py`. A symbolic identity that "obviously holds" is exactly the kind that hides a sign.

5. **Known-answer control (when feasible).** Periodically run this same protocol on a **deliberately flawed variant** of the proof (plant a subtle error) to confirm the verifier still catches planted errors. A verifier that passes everything is measuring nothing. This is cheap insurance on a headline claim.

---

## Oracle hierarchy

Every theorem-level claim in skill output must state the **highest tier it cleared**. The tiers are ordered by how much they constrain the space of ways the claim could still be wrong.

| Tier | Name | What it establishes | What it is silent on |
|---|---|---|---|
| **0** | Prover self-check | The prover re-read its own work. | Everything — near-worthless evidentially. Never sufficient. |
| **1** | Executable falsification | Deterministic scripts: small-case enumeration, symbolic identity checks, numeric bounds. Strong against a **false statement**. | Proof *validity* — a true statement can have a broken proof. |
| **2** | Independent LLM re-derivation | Clean-context, step-level, adversarial audit (the protocol above), same model family. Strong against **local logical gaps**. | Shared model-family blind spots. |
| **3** | Adversarial cross-model review | Tier 2 executed by a **different model family**. Currently the best available *soft* oracle. | Anything both families miss (rare but real). |
| **4** | Machine-checked formalization | Lean 4 + mathlib via Draft–Sketch–Prove (see `lean-bridge.md`). The only **hard** oracle. | Semantic faithfulness of the *formal statement* to the informal one — check that separately (see lean-bridge). And it is impractical for much of hard analysis. |

**Reach for Tier 4** on combinatorial, algebraic, number-theoretic, and discrete claims where mathlib coverage is plausible. **Do not force it** where the mathematics makes it impractical — a Tier-2/3 analysis proof honestly labeled beats a fake Lean sketch full of `sorry`.

### Output convention

Label every theorem the skill emits with the tier reached and the audit cost, e.g.:

```
Theorem 3 [verified: Tier 3, 4 rounds, 2 errors found and corrected]
Lemma 5  [verified: Tier 4, Lean/mathlib, statement-faithfulness checked]
Theorem 1 [verified: Tier 1 only — falsification survived; proof is Tier-0]  ← treat as conjectural
```

A claim that cleared only **Tier 0** must be labeled **conjectural**, not proved. A claim that cleared only **Tier 1** has survived falsification but has no validated proof — also conjectural until the proof clears Tier 2+.

---

## Reaching the tiers in practice

Tier 1 is executable scripts saved in the current project. Tier 4, when the math-prover plugin is loaded, is the `lean_check` tool (pinned Mathlib) with the `lean-formalizer` agent running the compile-fix loop. Tier 2/3 independent re-derivation maps onto spawning a fresh subagent with only the statement + proof text — keep its context clean. Record the tier reached in each step's grade and the write-up.
