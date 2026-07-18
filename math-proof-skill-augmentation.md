# Math Proof Skill — Augmentation Specification

**Purpose of this document.** You (Claude Code) are augmenting an existing skill for mathematical proof development. This document distills verified lessons from the 2024–2026 literature on LLM-assisted theorem proving into concrete modifications. Do not paste this document into the skill verbatim. Instead: read the existing SKILL.md, map each requirement below onto the existing structure, integrate where a phase already exists, and add what is missing. Preserve the skill's existing name, frontmatter, and any working machinery. Follow progressive-disclosure conventions: keep SKILL.md lean (<500 lines), push long protocols into `references/` files, and push deterministic checks into `scripts/`.

**Source basis.** The requirements below derive from documented successes and failure modes in: the GPT-5 science-acceleration case studies (arXiv:2511.16072), the Malliavin–Stein experiment (arXiv:2509.03065), the Gemini/Erdős-problems case study (arXiv:2601.22401), the FirstProof benchmark and responses (arXiv:2602.05192, arXiv:2602.21201), the LLM-generated Kochen–Specker paper with adversarial cross-model review (arXiv:2603.16988), process supervision ("Let's Verify Step by Step," arXiv:2305.20050), and Draft–Sketch–Prove (arXiv:2210.12283). Cite these in the skill's references section for provenance; do not rely on the model re-reading the papers at runtime.

---

## 1. Required workflow phases

Ensure the skill enforces the following phase sequence with explicit gates. If the existing skill already has phases, merge rather than duplicate; the gate conditions are the non-negotiable part.

### Phase 0 — Statement formalization and prior-art check
- Restate the claim precisely: hypotheses, conclusion, quantifiers, edge conditions. Ambiguity found here is cheaper than anywhere else.
- **Novelty gate:** before any proof attempt on a claim presented as new, search the literature (web search if available; otherwise flag as unverified). Documented failure mode: AI systems have "solved" open problems that were settled decades earlier, and ~2.5% of withdrawn arXiv math preprints duplicate prior results. The skill must never assert novelty without a recorded search, and must record the search terms used.
- Classify the claim: (a) known result to re-derive, (b) plausibly new, (c) open/conjectural. The classification changes the verification burden downstream.

### Phase 1 — Falsification before proof
- **Attempt to break the statement before proving it.** Search for counterexamples: small cases, degenerate/boundary cases, randomized instances, asymptotic sanity checks.
- Use executable tools, not mental arithmetic: SymPy/Sage/NumPy scripts for symbolic identities, numerical bounds, and small-case enumeration. Every numeric check must be a runnable script with a deterministic seed, saved to the working directory.
- Rationale: a proof attempt on a false statement is the most expensive failure, and it is where confabulation pressure on the model is highest. The successful published workflows (Malliavin–Stein, GPT-5 acceleration) all explored special cases and numerics before attempting the general argument.
- Gate: proceed to Phase 2 only after recording either "no counterexample found under checks X, Y, Z" or a refined statement that survives the checks.

### Phase 2 — Lemma-first proof sketch
- Produce a proof *sketch* before a proof: named lemmas, dependency order, and for each lemma the intended technique and difficulty estimate.
- Prove lemmas individually and **lock** them: once a lemma passes verification (Section 2), persist its statement and proof to a file and treat it as immutable unless a downstream contradiction forces reopening. Do not keep the whole proof state in conversation context — context degradation over long sessions is a documented reliability risk; files are the source of truth.
- Prefer strengthening a known qualitative result into a quantitative one, or generalizing a proved special case, over frontal assaults. This is the pattern behind every published LLM-derived new theorem to date.

### Phase 3 — Proof writing
- Write the full argument in standard mathematical prose with numbered steps or displayed equations sufficient that each inference is individually checkable.
- Every citation to an external result must include: exact statement as used, source, and a note on whether the source was actually consulted or is being recalled from memory. Recalled-from-memory citations are flagged `[UNVERIFIED-CITATION]` until checked. Silent reference fabrication is the single most common documented failure mode in LLM mathematical writing.

### Phase 4 — Verification (see Section 2 for the protocol)

### Phase 5 — Provenance log
- Emit a provenance artifact alongside the proof (e.g., `PROVENANCE.md`) recording: model/version, phase history, prompts or task descriptions for each phase, which verification tiers (Section 3) each claim cleared, errors found and in which round, and a partition of the final text into machine-generated / human-verified / machine-verified. The credible published papers all do this; it is becoming the publication norm and it is good epistemics regardless.

---

## 2. Verification protocol

Augment or replace the skill's verification step with the following. The design principle is **anti-circularity**: a verifier that shares the prover's derivation context inherits the prover's blind spots. Verification evidence is only as strong as the independence of the verifier.

1. **Step-level audit, not holistic review.** Walk the proof inference by inference; for each step, ask "does this follow from what precedes it, exactly as stated?" Process-level checking materially outperforms outcome-level checking (Lightman et al.). A verdict of "the proof looks correct overall" is not acceptable output.
2. **Independent re-derivation.** Spawn a fresh verification pass (subagent or new session) that receives *only* the theorem statement and the candidate proof — never the derivation history, scratch work, or the prover's stated confidence. Instruct it to actively hunt for errors, not to confirm.
3. **Adversarial rounds.** Run the independent audit for multiple rounds (default 3; more for a headline claim), fixing errors between rounds and re-auditing from scratch. Empirical basis: in the published Kochen–Specker workflow, adversarial cross-model review found substantive errors in rounds 2 and 5 — errors survive early rounds. If a second model family is available, use it for at least one round; if not, maximize independence via clean context and an explicitly adversarial system framing.
4. **Numeric spot checks on the final proof.** Re-run Phase 1 style checks against any intermediate quantitative claims (constants, exponents, inequality directions) that appear in the final argument. Inequality-direction and constant-tracking errors are the most common surviving defect class.
5. **Known-answer control (when feasible).** Periodically run the same verification protocol on a deliberately flawed variant of the proof to confirm the verifier still catches planted errors. A verifier that passes everything is measuring nothing.

## 3. Oracle hierarchy

Add an explicit hierarchy of verification strength, and require every theorem-level claim in skill output to state the highest tier it cleared:

- **Tier 0 — Prover self-check.** Necessary, evidentially near-worthless. Never sufficient.
- **Tier 1 — Executable falsification.** Deterministic scripts: small-case enumeration, symbolic identity checks, numeric bounds. Strong against false statements, silent on proof validity.
- **Tier 2 — Independent LLM re-derivation/audit.** Clean-context, step-level, adversarial (Section 2). Strong against local logical gaps, weaker against shared model-family blind spots.
- **Tier 3 — Adversarial cross-model review.** Tier 2 executed by a different model family. Currently the best available soft oracle.
- **Tier 4 — Machine-checked formalization.** Lean 4 + mathlib where practical, via the Draft–Sketch–Prove pattern (informal proof → formal sketch → tactic completion with compiler-error repair loops). This is the only hard oracle. Do not force it where the mathematics makes it impractical (much of hard analysis); do reach for it for combinatorial, algebraic, and discrete claims where mathlib coverage is plausible.

Output convention: e.g., `Theorem 3 [verified: Tier 3, 4 rounds, 2 errors found and corrected]`. Claims that cleared only Tier 0 must be labeled conjectural.

## 4. Behavioral rules (add to the skill's standing instructions)

- **Never present a proof with a known gap as complete.** Gaps are stated explicitly with a `[GAP]` marker and a description of what would close them. Pressure-induced confabulation — inventing a step to satisfy a request for completeness — is the failure the entire verification apparatus exists to catch; do not generate the failure.
- **Distinguish "I proved" from "I recall."** Any fact imported from training memory rather than derived or sourced in-session is marked as such.
- **Ask for counterexamples and simplifications, not just proofs.** When stuck, the productive prompts (per Tao's documented workflow and the published case studies) are: "find a counterexample," "prove the weakest nontrivial special case," "identify which hypothesis is doing the work," "simplify this argument." Encode these as the skill's stuck-state playbook.
- **Confidence honesty.** Report calibrated confidence per lemma, tied to oracle tier cleared — not a global confidence for the paper.

## 5. Bundled resources to add

Create or extend, following the skill anatomy conventions:

- `references/verification-protocol.md` — full Section 2/3 text, loaded only during Phase 4.
- `references/failure-modes.md` — the documented failure catalog: reference fabrication, already-solved "open" problems, inequality-direction errors, wishful verification, circular verification, context-degradation drift in long proofs. One paragraph each with the countermeasure.
- `references/lean-bridge.md` — Draft–Sketch–Prove procedure and mathlib search guidance; loaded only when Tier 4 is attempted.
- `scripts/numeric_check_template.py` — seeded template for falsification scripts (symbolic check, random-instance check, boundary-case sweep) so Phase 1 output is uniform and rerunnable.
- `scripts/provenance_init.py` (optional) — scaffolds `PROVENANCE.md` at session start.

## 6. Evaluation of the augmented skill

After integrating, validate the changes rather than trusting them:

1. Build a small ground-truth eval set: (a) true statements with known proofs at varying difficulty, (b) **false statements that look plausible** — these test the Phase 1 falsification gate, which is the highest-value addition, (c) statements that are true but were published long ago under different terminology — these test the novelty gate, (d) correct proofs with one planted subtle error — these test the Tier 2/3 audit.
2. Success criteria: false statements are caught in Phase 1 before proof attempts begin; planted errors are found within the default adversarial rounds; no novelty claim is emitted without a recorded search; every emitted theorem carries an oracle-tier label.
3. Run the pre-augmentation skill on the same set as a baseline if feasible; the deliverable of this exercise is a before/after on the error-catch rate, not a vibe check.

## 7. Integration checklist

- [ ] Read existing SKILL.md fully before editing; copy to a writable location if the installed path is read-only.
- [ ] Merge phases (Section 1) into the existing workflow without renaming the skill or breaking existing triggers.
- [ ] Add the verification protocol and oracle hierarchy (Sections 2–3), moving long text to `references/`.
- [ ] Add behavioral rules (Section 4) to standing instructions.
- [ ] Create bundled resources (Section 5).
- [ ] Keep SKILL.md under ~500 lines post-merge; verify the frontmatter description still triggers correctly for proof-related prompts.
- [ ] Build the eval set and run the validation in Section 6; report results before finalizing.
