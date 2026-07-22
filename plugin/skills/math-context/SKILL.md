---
name: math-context
description: Build full mathematical context for a statement before proving it - MSC field classification, the accumulated field playbook, similar known conjectures from the OpenConjecture map, literature search, and precise definitions. Use when the user asks to classify, contextualize, or gather background for a mathematical statement or conjecture, or before attacking a nontrivial claim with prove-conjecture.
---

# Build mathematical context

Assemble everything known and relevant about a mathematical statement before
any proof work — the CLI analog of the proof workspace's discovery pass. The
tools referenced here come from the math-prover plugin (`msc_search`,
`msc_validate`, `query_knowledge`, `record_knowledge`, `similar_conjectures`,
`conjecture_context`, `lean_check`) and TheoremSearch (`theorem_search`).
If one is unavailable, skip its step and say so — do not fake its output.

## Protocol

1. **Classify the field, granularly.** Extract the statement's key concepts;
   `msc_search` each to find candidate MSC 2020 codes; choose the 1–2 most
   specific codes that *genuinely* fit (leaf level when possible) and confirm
   with `msc_validate`. Add a free-text refinement when the sub-area is
   sharper than MSC resolves (e.g. "Szemerédi-type density arguments").

2. **Pull the field playbook.** `query_knowledge(code=<primary>)` walks
   leaf → subclass → class; also run a keyword pass
   (`query_knowledge(query=…)`). Respect provenance labels: entries marked
   recalled/unverified are candidate knowledge, not established fact. If the
   field has no playbook yet, note that — a later look-back should seed it.

3. **Nearest known conjectures.** `similar_conjectures(statement)`; for the
   top 2–3 genuinely relevant hits, `conjecture_context(node_id)` for their
   neighbors, shared objects, and classified logical relations.

4. **Literature.** `theorem_search` with 2–3 phrasings of the statement and
   its key lemmas. Record the search terms used — this is the novelty-gate
   discipline: never assert a claim is new without a recorded search.

5. **Definitions.** Unfold every mathematical object in the statement:
   precise definition, the role it plays here, and any ambiguous readings
   (state the reading you adopt).

6. **Deliver the context brief** (in conversation, or as a file if asked):
   - the pinned-down statement (hypotheses ⇒ conclusion, quantifiers explicit)
   - classification: MSC codes + names + refinement; known / plausibly new /
     open, with the novelty-gate search terms
   - playbook highlights (entry ids, provenance labels)
   - nearest map conjectures with their relations
   - literature hits — consulted vs. recalled clearly marked
   - definitions
   - suggested attack angles, each tied to a playbook technique or a
     harvested proof where possible

## Contribution discipline (keep the knowledge base alive)

- After a session that actually establishes something, run the look-back:
  `query_knowledge` first, then `record_knowledge(origin='session')` for
  what generalizes — techniques that worked, reusable lemmas, pitfalls hit,
  counterexample patterns. Writes are attributed to this CLI session
  automatically.
- Refine existing entries via `entry_id`; never duplicate.
- `origin='seeded'` only when creating a fresh field's initial playbook
  (3–6 entries: standard techniques, default assumptions, known pitfalls) —
  these stay labeled recalled/unverified until a real proof confirms them.
- `origin='theoremsearch'` for literature hits durable for the *field*, not
  just the current problem.
