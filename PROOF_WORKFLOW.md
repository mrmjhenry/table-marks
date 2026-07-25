# Proof Workflow

How we take a theorem, conjecture, or lemma from "here's a statement" to a verified proof,
a machine-readable record, and a visualization-heavy PDF explainer.

This is the process document. It is written to be **replicable by someone else** — see
[Prerequisites](#prerequisites) for what the machinery needs and
[Adapting this elsewhere](#adapting-this-elsewhere) for what to do when you don't have it.

---

## Table of contents

- [What this is](#what-this-is)
- [Prerequisites](#prerequisites)
- [The four standing decisions](#the-four-standing-decisions)
- [The pipeline](#the-pipeline)
- [Working modes](#working-modes)
- [Model escalation](#model-escalation)
- [Artifacts on disk](#artifacts-on-disk)
- [`meta.json` schema](#metajson-schema)
- [Knowledge base discipline](#knowledge-base-discipline)
- [Adapting this elsewhere](#adapting-this-elsewhere)

---

## What this is

A research-grade proof protocol (from the `math-prover` plugin's `prove-conjecture` skill,
which is built on Fernández-León et al. CERME10 2017, Pólya, Lakatos, Thurston, Gowers, and
modern AI-prover practice) wrapped in a **learning-oriented** shell: the human presenting the
theorem wants to *understand* it, not just possess a proof of it.

That shapes three things the bare protocol doesn't specify: a spoiler policy, a choice of how
much of the proof the human drives, and a visualization pass at the end.

The non-negotiable core, inherited from the skill:

- **Falsification before proof.** Never attempt a proof before trying to break the statement.
- **Grade every claim** `verified` / `partially verified` / `unverified`, and label it with the
  **oracle tier** it cleared: 0 self-check · 1 executable falsification · 2 independent
  re-derivation · 3 cross-model adversarial · 4 machine-checked (Lean).
- **Files are the source of truth**, not conversation context. Locked lemmas go to disk.
- **`[GAP]` markers are never silently closed.** A known gap presented as complete is the
  failure mode the whole apparatus exists to prevent.
- **Citations are marked consulted vs. recalled.** Anything from training memory is
  `[UNVERIFIED-CITATION]` until checked.

---

## Prerequisites

| Component | What it provides | If missing |
|---|---|---|
| `math-prover` plugin | `msc_search`, `msc_validate`, `query_knowledge`, `record_knowledge`, `similar_conjectures`, `conjecture_context`, `lean_check`; the `lean-formalizer` agent; three skills | Core protocol still runs; you lose classification, the shared playbook, and Tier 4 |
| A local **Lean 4 + Mathlib** toolchain (the plugin pins one) | `lean_check` — the only *hard* oracle | Ceiling drops to Tier 3. Say so; do not label a result Tier 4 |
| The **`math_geneology`** repo + its venv | Backs the `proof` MCP server (KB + OpenConjecture map + Lean) | KB and map steps skipped |
| **TheoremSearch** MCP (`api.theoremsearch.com`) | Literature search / novelty gate | Substitute web search; record the terms either way |
| **TeX Live** + `pdflatex` | Builds the PDF explainer | Report + `meta.json` still produced |
| Python (SymPy / NumPy) | Executable falsification scripts — Tier 1 | **Do not substitute mental arithmetic.** Without this, Tier 1 is unreachable |

> **Machine-bound warning.** In this installation the `proof` MCP server is hardwired to an
> absolute path (`<home>/Desktop/code/math_geneology/.venv`) in
> `~/.claude/skills/math-prover/.mcp.json`. Anyone replicating this must clone that repo and
> repoint those paths, or accept a Tier-3 ceiling.

**Degradation rule:** if a tool is unavailable, skip its step and *say so in the report*.
Never fake a tool's output.

---

## The four standing decisions

These were settled once and apply to every problem unless overridden per-problem.

### 1. Spoilers: look, but don't tell

During Phase 0 the assistant **reads** known proofs (`theorem_search`, `similar_conjectures`,
literature) so its hints are informed rather than random — but **does not show them** to the
learner. The learner can say *"spoil it"* at any moment to unlock them.

After sign-off, we deliberately **compare our proof to the standard one**. That comparison is
often the most instructive part of the whole exercise and belongs in the report's narrative.

### 2. Depth: always full protocol

Every problem gets the full Phase 0–5 treatment — novelty gate with recorded search terms,
three adversarial audit rounds, complete evidence log, `PROVENANCE.md` — regardless of whether
it is a textbook exercise or an open problem. Uniformity is chosen deliberately so that every
report is directly comparable in the dashboard.

**Cost note:** on a known textbook lemma the novelty gate resolves to "known result,
classification (a)" and the extra audit rounds are largely ceremony. Accepted for consistency.
**Per-problem override:** the learner can say *"light pass"* to drop to one audit round and no
provenance log; the report records that it ran reduced.

### 3. Lean: incremental, with a tractability call

- Formalize **each lemma as it locks**, not the whole proof at the end. Late formalization
  failures can invalidate an entire chain, and the Draft–Sketch–Prove skeleton is most useful
  while the argument is still soft.
- Use the **`lean-formalizer` agent**, which owns the compile-fix loop against pinned Mathlib.
  Budget ~8 compile iterations per statement.
- **A green compile is not verification.** The faithfulness check is a separate, manual,
  non-skippable step: same quantifiers, same hypotheses, no vacuous premise, no `ℕ` where `ℤ`
  was meant, no silently truncating natural subtraction or division. Optionally attempt to
  prove the *negation* as a falsification filter — if it closes easily, the formal statement is
  wrong, not the mathematics.
- If a statement won't close after the budget: emit `[GAP]`, keep the honest tier, and **never**
  leave a `sorry` and call the proof done.
- Group theory and algebra have strong Mathlib coverage, so Tier 4 is usually reachable here.
  Where it isn't, an honest Tier 3 beats a `sorry`-padded file.

### 4. Artifacts: both a PDF and a machine record

Every completed problem produces a human-facing **visualization-heavy LaTeX PDF** *and* a
machine-readable **`report.md` + `meta.json`**. See [Artifacts on disk](#artifacts-on-disk).

---

## The pipeline

Gates marked **🚦 GATE** require explicit human sign-off before proceeding.

### Phase 0 — Pin the statement and build context

1. Restate as a precise conditional: hypotheses ⇒ conclusion, every quantifier explicit.
2. Unfold every definition; where a term is ambiguous, state the reading adopted. (Ambiguity
   found here is far cheaper than ambiguity found in Phase 3.)
3. Classify: `msc_search` the key concepts → 1–2 most specific MSC 2020 codes → `msc_validate`.
   Add a free-text refinement where MSC is too coarse.
4. `query_knowledge(code=…)` **and** `query_knowledge(query=…)` — pull the field playbook
   *before* re-deriving any standard technique. Respect provenance labels: `seeded`/recalled
   entries are candidate knowledge, not fact.
5. `similar_conjectures(statement)`; `conjecture_context(node_id)` on the top 2–3 hits.
6. **Novelty gate:** `theorem_search` with 2–3 phrasings, record the exact search terms, and
   classify as (a) known result to re-derive, (b) plausibly new, (c) open. *This is also where
   the spoiler lookup happens — the assistant reads, the learner doesn't see.*
7. Identify boundary and degenerate cases of the hypothesis space.

> **🚦 GATE 1 — Statement confirmed.** Present the pinned statement, the definitions as adopted,
> and the classification. The learner confirms this is what they meant. A mis-pinned statement
> invalidates everything downstream, and this gate is the cheapest in the process.

### Phase 1 — Horizontal exploration (falsify first)

**Try to refute before trying to prove.** Randomized instances, boundary and degenerate cases,
glued/composite constructions, exhaustive enumeration of small cases. Use **executable scripts**
(seeded, saved to `scripts/`) — never mental arithmetic. Each script becomes a regression check
if the statement is later revised.

A conjecture that *survives* a hostile search usually reveals, in the pattern of near-failures,
the structural property the proof will turn on. For a learner this is where the question "what
is this hypothesis actually doing?" gets answered.

Then, interleaving freely: detect patterns in concrete objects; harvest techniques *and whole
proofs* from neighboring results (transplant-and-repair material); mine the literature for
implicit corollaries.

Maintain an **evidence log** — every example tested, what was computed, verified or refuted,
patterns noticed, each entry graded. Inconclusive experiments are logged as inconclusive.

**Exit condition:** record either "no counterexample found under checks X, Y, Z" (name them) or
a refined statement that survives. Surviving falsification clears **Tier 1** — evidence the
statement is *true*, silent on whether any proof is *valid*.

> **🚦 GATE 2 — Mode choice.** Now that we know whether it's true and roughly how hard it is,
> the learner picks a working mode (see [Working modes](#working-modes)). Asking before this
> point asks them to choose blind.

### Phase 2 — Vertical formalization

- **Draft → sketch-with-holes → close the holes.** Write the informal idea, convert it to a
  proof sketch with *named open subgoals*, then attack the subgoals. This beats attacking the
  target directly, and the named subgoals are exactly what the learner picks from in
  subgoal-split mode.
- **Lock each proved lemma to disk** and treat it as immutable unless a downstream contradiction
  forces explicit reopening. Formalize it in Lean at this point (decision 3).
- Prefer strengthening/generalizing a proved case over a frontal assault.
- Generate auxiliary problems freely — but **integration is its own step**: after solving one,
  explicitly work out how it serves the main proof before counting it as progress.
- Choose a demonstration method deliberately (direct, contrapositive, contradiction, induction,
  exhaustion, construction) with a reason tied to the statement's logical shape.
- When chaining known results, verify at **every link** that the cited theorem's hypotheses
  actually hold in this setting. This is where most plausible-looking proofs die.
- **Every step needs a discovery rationale** — a plausible account of how someone could have
  thought of it. In a learning context this is the whole point: a step with no motivation is a
  rabbit from a hat, and it neither teaches nor generalizes.

**Stuck-state playbook** (before pushing harder): look for a counterexample; prove the weakest
nontrivial special case; identify which hypothesis is doing the work; simplify the argument. If
most of the effort has gone into direct proving and it's stalled, return to Phase 1 — in the
empirical record, direct proof steps are a *minority* of productive activity.

### Phase 3 — Counterexample handling

Run the **Lakatos diagnostic** as two independent questions:

- Does it refute the **conjecture** (global)?
- Does it refute a **step of the current proof** (local)?

| Diagnosis | Route |
|---|---|
| Local, not global | Conjecture survives; repair or replace the step. Statement unchanged. |
| Global *and* local | Guilty step identified → **lemma-incorporation**: build its condition into the hypotheses. |
| Global, not local | The proof "succeeds" on a false statement → a **hidden lemma** is in use. Surface the implicit assumptions as explicit steps, re-run the diagnostic. |

Repair operations, in order of preference: **lemma-incorporation** → **exception-barring**
(restrict the domain, as little as the evidence requires) → **monster-barring** (sharpen an
ambiguous definition — legitimate only if the concept genuinely was ambiguous, and *always*
flagged as a definition change) → **surrender** (record why).

Every revision is **tracked**: `meta.json` carries a `statement_revisions` array, and the
revised statement restarts Phase 1 using the saved scripts as regression checks.

### Phase 4 — Verification

Verification is only as strong as the verifier's **independence from the prover**. Run all of
these; they do not substitute for one another.

*Content checks:*

1. **Idea-level weakness hunt** — which step would an expert distrust? Where is it thinnest?
   Which inequality or limit exchange is most suspicious?
2. **Step-level checks**, not holistic review. Verify each inference exactly as stated, and
   instantiate steps on concrete objects. Confirm every sub-argument ends on *exactly* the goal
   it opened with — landing somewhere adjacent is a classic hidden failure.
3. **Test consequences against independent knowledge** — known special cases, asymptotics,
   numerics, dualities.
4. **Re-run numeric checks** against every quantitative claim surviving into the final argument
   (constants, exponents, inequality directions, factor-of-two errors).

*Independence checks:*

5. **Independent re-derivation.** Spawn a subagent given **only the statement and the candidate
   proof** — never the derivation history, the scratch work, or the prover's confidence.
   Instruct it to *hunt for errors*, not confirm.
6. **Three adversarial rounds** (per decision 2), fixing and re-auditing from scratch between
   rounds. Substantive errors routinely survive to round 2+. Run at least one round on a
   different model (see [Model escalation](#model-escalation)) — that is what makes it Tier 3.

Then **look back**: what generalizes? Which lemmas are reusable? Did the proof's actual working
conditions define a sharper concept than the statement's (the uniform-convergence pattern)? If
so, propose the redefinition and the reshaped theorem.

**Figure log.** Throughout Phases 1–4, record every diagram that would explain something —
subgroup lattices, orbit pictures, commutative diagrams, Cayley graphs. The diagram that
*explains* a proof is usually the one that *found* it, and capturing them live makes the
Phase 6 discussion a curation pass instead of a cold brainstorm.

### Phase 5 — Provenance

Emit `PROVENANCE.md` (scaffold: `python3 provenance_init.py "<title>" --out PROVENANCE.md`):
model and version, phase history, the novelty-gate search terms, the per-claim verification
ledger (tier reached, rounds run, errors found and in which round), citations with
consulted-vs-recalled status, and the machine-generated / machine-verified / human-verified
partition of the final text.

Run the knowledge-base look-back here — see
[Knowledge base discipline](#knowledge-base-discipline).

### Phase 6 — Visualization and report

1. **Discuss visualizations** with the learner, working from the figure log. Which diagrams
   carry the argument? What would make the mechanism visible rather than merely stated?
2. Draft the report and the TikZ figures.

> **🚦 GATE 3 — Report sign-off.** Nothing is built until the learner approves the
> visualization plan and the report content.

3. Build: `report.md` + `meta.json` + the LaTeX PDF (`./build.sh <slug>`).
4. Verify the PDF visually — `pdftoppm -png -r 70 <slug>.pdf page` and inspect the pages.
5. Add the explainer to the `one-offs/README.md` index.

---

## Working modes

Chosen at **Gate 2**, after exploration, and **revisitable at any time** — the learner can
switch mid-proof without restarting.

| Mode | How it works | Best for |
|---|---|---|
| **Step-by-step** | The learner names the next step; the assistant executes, checks it, and reports what it opens or closes. | Building proof intuition; when the learner wants to own the strategy. |
| **Subgoal split** *(recommended)* | The assistant produces the Phase 2 sketch with named open subgoals; the learner picks which to close personally, the assistant takes the rest. | Most learning per unit time — the learner owns the interesting content, not the bookkeeping. |
| **Full solve** | The assistant proves it end to end, then walks through the reasoning. | Hard results where the goal is the write-up, or when time is short. |

---

## Model escalation

**Trigger (concrete, not vibes):** two complete horizontal↔vertical cycles with no movement on
the *same* subgoal, or a subgoal that has survived three distinct attack approaches.

**Handoff discipline — escalate as a fresh attempt, not a rescue.** Hand the stronger model the
*pinned statement, the evidence log, and the named obstruction*. **Do not** hand over the full
transcript: a stronger model inheriting a stuck framing tends to inherit the dead end.

**Escalate the auditor too — often the higher-value use.** A stronger or different-family model
running an adversarial round is exactly what promotes a result from Tier 2 to **Tier 3**. In
practice, a stronger model finds more as a skeptic than as a prover.

Mechanically: `Agent` with `model: "fable"` (or another tier) for a subagent, without the
learner needing to switch their own session model. `meta.json` records which model proved and
which models audited.

---

## Artifacts on disk

Flat directory, one shared style — the `one-offs/` convention.

```
one-offs/
├── algebra-style.sty          # shared style (verbatim copy of the chapter style)
├── build.sh                   # ./build.sh <slug>  or  ./build.sh for all
├── README.md                  # index of explainers
├── PROOF_WORKFLOW.md          # this document
├── <slug>.tex                 # the explainer source
├── <slug>.pdf                 # the human-facing artifact — built from the signed-off report
└── <slug>/                    # the machine record
    ├── report.md              # audit trail (proof-report skill format)
    ├── meta.json              # dashboard join key — see schema below
    ├── PROVENANCE.md          # Phase 5 provenance log
    ├── figures.md             # the figure log
    ├── lean/<slug>.lean       # formalization(s)
    └── scripts/*.py           # falsification + regression checks
```

**One slug per problem**, used consistently across the `.tex`, the directory, the Lean file, and
the `meta.json` — this is what makes the dashboard join trivial.

The PDF is the **teaching artifact**: visualization-first, TikZ / tikz-cd / pgfplots carrying the
explanation rather than decorating it, never ASCII diagrams. The `report.md` is the **audit
trail**: complete, self-contained, faithful to the record.

---

## `meta.json` schema

Emitted for **every** problem, from the very first one. Retrofitting structure onto twenty prose
reports later is painful; emitting it now is free. This is the contract the dashboard consumes.

```jsonc
{
  "slug": "cauchy-theorem",
  "title": "Cauchy's Theorem",
  "statement_tex": "If $G$ is a finite group and $p \\mid |G|$ is prime, then $G$ has an element of order $p$.",
  "status": "proved",                     // proved | refuted | partial
  "protocol": "full",                     // full | light
  "date_started": "2026-07-25",
  "date_completed": "2026-07-26",

  "msc": [{ "code": "20D99", "name": "Abstract finite groups — misc." }],
  "msc_refinement": "Sylow-adjacent counting arguments",

  "novelty": {
    "classification": "known",            // known | plausibly_new | open
    "search_terms": ["Cauchy theorem finite group element of order p", "McKay proof Cauchy"],
    "tools_used": ["theorem_search", "similar_conjectures"]
  },

  "max_oracle_tier": 4,
  "claims": [
    { "id": "st_001", "statement": "...", "grade": "verified", "tier": 4,
      "lean_file": "lean/cauchy.lean", "discovery_rationale": "..." }
  ],
  "gaps": [],                             // any [GAP] markers surviving into the final text

  "lemmas_introduced": [
    { "id": "lem_001", "statement_tex": "...", "reusable": true, "kb_entry_id": "kb_0412" }
  ],
  "counterexamples": [
    { "against": "original statement", "diagnostic": "local", "repair": "lemma-incorporation" }
  ],
  "statement_revisions": [
    { "from_tex": "...", "to_tex": "...", "reason": "...", "phase": 3 }
  ],

  "lean": {
    "attempted": true, "status": "ok",    // ok | has_sorries | failed | not_attempted
    "file": "lean/cauchy.lean",
    "faithfulness_checked": true,
    "faithfulness_note": "Quantifiers match; |G| as Nat.card; p prime hypothesis explicit; no vacuity.",
    "negation_filter_run": true
  },

  "audit_rounds": [
    { "round": 1, "model": "claude-opus-5", "independent_context": true, "errors_found": 2 },
    { "round": 2, "model": "claude-opus-5", "independent_context": true, "errors_found": 1 },
    { "round": 3, "model": "claude-fable-5", "independent_context": true, "errors_found": 0 }
  ],
  "models": { "prover": "claude-opus-5", "auditors": ["claude-opus-5", "claude-fable-5"] },
  "escalated": false,

  "mode": "subgoal_split",                // step_by_step | subgoal_split | full_solve
  "spoiler_policy": "look_dont_tell",
  "learner_closed_subgoals": ["lem_001"],

  "figures": [
    { "id": "fig-orbit", "caption": "...", "kind": "tikz", "carries": "the counting argument" }
  ],
  "kb_entries_recorded": ["kb_0412"],
  "citations": [
    { "text": "McKay, 'Another proof of Cauchy's group theorem'", "consulted": true }
  ],

  "artifacts": {
    "pdf": "../cauchy-theorem.pdf", "report": "report.md",
    "provenance": "PROVENANCE.md", "figure_log": "figures.md"
  }
}
```

**Dashboard handoff.** When aggregating, hand Claude Design the set of `meta.json` files plus
this schema section. Everything the dashboard needs — status distribution, tier distribution,
MSC coverage, lemma reuse graph via `kb_entry_id`, escalation rate, audit-round error decay,
learner participation via `learner_closed_subgoals` — is derivable without parsing prose.

---

## Knowledge base discipline

Two named checkpoints, so this doesn't silently never happen:

- **Phase 0 (read):** `query_knowledge(code=…)` and `query_knowledge(query=…)` *before*
  re-deriving any standard technique. The KB walks leaf → subclass → class.
- **Phase 5 (write):** `record_knowledge(origin='session')` for what this session actually
  established — techniques that worked, reusable lemmas, pitfalls hit, counterexample patterns.

Rules:

- Record only what cleared **Tier ≥ 2**. The KB is shared; unverified material pollutes it.
- Refine existing entries via `entry_id` — **never duplicate**.
- `origin='seeded'` only when creating a fresh field's initial playbook; those stay labeled
  recalled/unverified until real work confirms them.
- `origin='theoremsearch'` for literature hits durable for the *field*, not just this problem.
- Log the returned entry ids into `meta.json` (`kb_entries_recorded`) so reuse is traceable.

---

## Adapting this elsewhere

If you're replicating this without the full setup:

1. **No `math-prover` plugin?** The pipeline still works. Replace `msc_search`/`query_knowledge`
   with your own notes, `theorem_search` with web search, and cap the oracle tier at 3. Keep the
   falsification-first rule and the grading — those carry most of the value.
2. **No Lean?** Cap at Tier 3 and say so explicitly in every report. An honest Tier 3 is worth
   more than a fake Tier 4.
3. **Different subject?** Nothing here is algebra-specific except the observation that Mathlib's
   group-theory coverage makes Tier 4 unusually reachable. In hard analysis expect Tier 3.
4. **Not a learner?** Drop the spoiler policy and the mode choice; run full-solve with the
   research protocol as written.
5. **Keep `meta.json` regardless.** It is the cheapest part of this process and the only reason
   aggregation across problems is tractable later.

The one thing not to drop: **independence of the verifier from the prover**. A verifier that
shares the prover's context inherits its blind spots, and reviewing your own proof until it
looks convincing is not verification.
