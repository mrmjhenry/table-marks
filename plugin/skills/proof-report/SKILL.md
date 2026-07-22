---
name: proof-report
description: Generate a self-contained proof report from a proof developed in this conversation - narrative, graded steps with oracle tiers, evidence, Lean appendix, and a provenance section. Use when the user asks to write up, export, or produce a report of a proof.
---

# Proof report

Produce a standalone write-up of a proof developed in this conversation,
faithful to the record. Default output: `./proof-report-<slug>.md` in the
current project (ask before overwriting an existing file). If the user wants
HTML, wrap the same content in a minimal single-file page (KaTeX via CDN
links is acceptable there; keep it simple).

## Required sections, in order

1. **Header** — title; the final precise statement (TeX); status:
   **proved / refuted / partial**; date; how it was produced (this
   conversation, tools used).
2. **Narrative** — the story of the proof: strategy and why it was the
   natural choice, key ideas, how the argument unfolded (gaps caught and
   repaired, Lakatos events with their diagnostics), what the executable
   checks established (and their limits — a finite sweep is evidence, not
   proof), and how any Lean formalization corresponds to the informal
   argument (faithfulness subtleties included).
3. **The proof** — numbered steps: statement, justification, grade
   (verified / partially verified / unverified / refuted), and the oracle
   tier reached (0 self-check · 1 executable falsification · 2 independent
   audit · 3 cross-model · 4 machine-checked).
4. **Evidence** — every check run: scripts (inline or referenced with their
   key output), computations, citations with hypotheses-checked status.
5. **Counterexamples** (if any) — each with its Lakatos diagnostic
   (global/local) and the repair taken.
6. **Lean appendix** (if Tier 4 was reached) — the code, the compile result,
   and the faithfulness note (why the formal statement matches the informal
   one).
7. **Provenance** — per-claim oracle tiers; the machine-checked vs.
   argued-informally partition; novelty-gate search terms used; every
   citation marked consulted vs. recalled (`[UNVERIFIED-CITATION]` if never
   checked); knowledge-base entries recorded from this session (ids).

## Rules

- Accuracy over flourish: describe only what the conversation's record
  supports. Never present an unverified step as established, a `[GAP]` as
  closed, or a claim above the tier it actually cleared.
- A claim that cleared only Tier 0 is **conjectural** — label it so.
- Keep the report self-contained: a reader without this conversation must
  be able to follow the proof and audit its provenance.
