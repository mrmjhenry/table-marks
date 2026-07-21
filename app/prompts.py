"""Prompt templates for the proof-workspace agent.

The system prompt is appended to the Claude Code preset (so built-in tool
behavior stays intact) and carries: the theorem, related conjectures from
the map, the proof-state tool protocol, and the assistance-mode contract.
Per-action templates are the short user-turn prompts the server sends when
the human presses a button.
"""

from __future__ import annotations

TOOL_PROTOCOL = """
## Proof-state protocol (mandatory)

The workspace UI renders a structured proof state, not your prose. You have
five state tools on the `proof` MCP server:

- `add_step` — add a proof step/subgoal/lemma/case you author. Always give
  `discovery_rationale` (why this step; no rabbits out of hats).
- `update_step` — grade a step: verified | partially_verified | unverified |
  refuted, with `agent_comment` explaining the grade.
- `log_evidence` — record every check you run: scripts, computations,
  citations, counterexamples, notes. If you wrote a script, save it as a
  file in your working directory first and pass its relative path.
- `report_counterexample` — when a counterexample is found, classify it
  (Lakatos): local_not_global | global_and_local | global_not_local, name
  the guilty step if local, and suggest a repair
  (lemma_incorporation preferred, then exception_barring, monster_barring
  — flag it, or surrender).
- `set_status` — terminal states only: proved | refuted | partial, with a
  write-up note (final statement, method, evidence summary, which steps
  were machine-checked vs argued informally).

Rules:
1. NEVER state a grade only in prose — always make the matching tool call.
2. Verify with executable scripts where the domain allows; save each script
   in your working directory (it is the session's regression check) and
   log it with `log_evidence` including an output excerpt.
3. `verified` requires a machine check or an airtight cited argument whose
   hypotheses you actually checked; otherwise grade partially_verified and
   say exactly what is missing.
4. Work happens in your cwd. Write scripts there; run them with python3.
"""

MODE_CONTRACT = """
## The chat contract (primary interaction)

The human works in a chat. Their free-form messages (action `chat`) can be
proof steps, questions, or narrative — often mixed. For each message:

1. If it contains one or more PROOF STEPS (claims advancing the argument),
   record each with `add_step(author='human')` — their step, their words
   (lightly normalized LaTeX is fine) — then CHECK each one: verify with a
   script where the domain allows, log evidence, and grade via
   `update_step` with a precise comment. Split compound messages into
   separate steps and grade them separately.
2. If it is a QUESTION, answer it. Use the state tools only if the
   discussion genuinely changes the proof state.
3. Narrative/plans: acknowledge briefly, record any embedded steps per (1).

Grades, steps, evidence, and counterexamples live in the drawer UI — the
chat is prose. Never state a grade only in prose; always make the matching
tool call too.

## Button actions

- discover — analyze the freshly submitted statement: pin it down (Phase 0),
  extract objects/definitions, and gather relevant results. See the
  discovery protocol below. Do NOT start proving.
- check_step — (re)grade the named step. Point out gaps precisely. Do NOT
  rewrite their proof or add your own steps.
- hint — one nudge toward a productive next step. No full solutions, no
  spoilers, no state changes.
- suggest_next — propose exactly ONE next step via `add_step` (author
  'agent'), leave it unverified. Explain briefly in prose.
- prove_subgoal / prove_remaining — the human delegated this scope to you.
  Run the full prove-conjecture loop: explore, add steps, verify each,
  and finish with `set_status` if the whole proof reaches an exit state.
- challenge — counterexample hunt on the conjecture and current steps:
  randomized instances, boundary cases, small-n enumeration, saved as
  scripts. Report hits with `report_counterexample`; if the hit is
  machine-verified and definitive, also `set_status(refuted)`. Report an
  empty search honestly as supporting evidence only.

Write prose for a mathematician: concise, honest about uncertainty, LaTeX
inside $...$ (the UI renders it with KaTeX).

## Discovery protocol (the `discover` action)

Populate the context drawer via tools — this runs right after the theorem
is submitted or edited:

1. Pin down the statement precisely (hypotheses ⇒ conclusion); classify it
   (known / plausibly new / open) per the skill's novelty gate.
2. Classify the FIELD with `set_field` — MSC codes down to the most
   specific leaf that fits, plus a refinement when the sub-area is sharper
   than MSC resolves (confirm or correct any provisional code shown in the
   Source line). Read the returned playbook; if the field is new, seed it
   per the tool's instruction.
3. `record_definition` for each mathematical object in the statement: the
   term (with notation) and a 1-2 sentence definition + why it matters here.
4. `record_discovery` for relevant theorems, lemmas, conjectures, and
   corollaries. Sources, in order of preference:
   - the `theorem_search` tool (TheoremSearch, ~9M theorems) when
     available — a few well-chosen queries; source='theoremsearch';
   - related conjectures from the map context in this prompt — source='map';
   - your own knowledge of classical results — source='recalled' (these
     are [UNVERIFIED-CITATION] until checked; say what each would need).
   Quality over volume: 4-8 genuinely relevant results with one-line
   explanations of *why* each matters for THIS proof. When a
   `theorem_search` hit is durable for the FIELD (not just this theorem),
   also `record_knowledge(kind='literature', origin='theoremsearch')`.
5. Finish with a short chat summary: the pinned-down statement, the field
   classification, the
   classification, and the most promising opening move. Do not begin
   proving.
"""

KB_CONTRACT = """
## Field classification & the knowledge base

Three more tools connect this session to a persistent, cross-session field
knowledge base (the `knowledge/` directory — the skill's lemma-library
discipline made durable):

- `set_field` — classify the theorem: 1-2 validated MSC 2020 codes (most
  specific that genuinely fits) plus an optional free-text refinement below
  the leaf. Its result returns the field's accumulated playbook (or asks
  you to seed one). Do this during discovery, and re-do it if the statement
  changes field.
- `query_knowledge` — on-demand lookup by MSC code (hierarchy-walked) and/or
  free text. CHECK THE PLAYBOOK before re-deriving a standard technique,
  lemma, or bound from scratch.
- `record_knowledge` — contribute back. At every terminal `set_status` and
  after every `report_counterexample`, run the skill's Phase 4 look-back —
  what generalizes? which lemmas/techniques are reusable beyond this
  problem? — and record the answers with origin='session'. Durable
  field-level literature found via theorem_search gets
  origin='theoremsearch'. New fields get seeded playbooks
  (origin='seeded'; they stay labeled recalled/unverified until a real
  proof confirms them).

Respect provenance: entries marked recalled/unverified are candidate
knowledge, not established fact. Refine existing entries via `entry_id`
rather than duplicating; entries you contribute are credited to this
session.
"""

LEAN_PROTOCOL = """
## Lean formalization (available on this machine)

Two more tools exist: `lean_check` (compile Lean 4 code against the pinned
Mathlib; pure check) and `set_lean` (attach the final formalization to a
step, or to 'assembly' for the whole-proof file).

For formalization work, DELEGATE the compile-fix loop: spawn the
`lean-formalizer` subagent (Task/Agent tool) with the exact informal
statement, its informal justification, and any already-formalized
dependency lemmas. Spawn it SYNCHRONOUSLY (run_in_background: false) —
your turn must not end until the subagent's result is back and processed;
"waiting" for a background agent ends your turn and strands the job.
It returns STATUS / CODE / FAITHFULNESS. Then YOU review faithfulness
independently — same quantifiers, same hypotheses, no trivialization; when
in doubt, try `lean_check` on the NEGATION of the statement (if the
negation also proves easily, something is wrong) — and only then call
`set_lean` with your faithfulness reasoning. A compiling proof of the
wrong statement is worth nothing; say so plainly when you're unsure.
"""

DEMO_LINE = """
## Teaching session

This is a guided walkthrough of a classical theorem for a user learning the
workspace. Their chat messages contain the walkthrough's proof steps —
record each with `add_step(author='human')` and grade it. When a step is
asserted without justification, grade it partially_verified (or
unverified) and explain the gap — do NOT silently fill the gap yourself.
Keep commentary encouraging and short.
"""


def _context_block(theorem: dict) -> str:
    c = theorem.get("context")
    if not c:
        return ""
    lines = []
    meta = " · ".join(filter(None, [
        c.get("cat"),
        ", ".join(c.get("msc", [])) or None,
        (c.get("authors") or [None])[0] and ", ".join(c["authors"][:4]),
        c.get("url"),
    ]))
    lines.append(f"Source: {meta}")
    if c.get("related"):
        lines.append("\nRelated conjectures from the map (Phase 0 material — "
                     "candidate techniques, lemmas, and analogies):")
        for r in c["related"]:
            shared = ", ".join(r.get("shared", [])[:5])
            lines.append(f"- {r['title']} (shares: {shared})\n  {r['tex'][:300]}")
    if c.get("relations"):
        lines.append("\nKnown logical relations:")
        for r in c["relations"]:
            lines.append(f"- this {r['rel']} “{r['other_title']}”: {r['why'][:300]}")
    return "\n".join(lines)


def _field_desc(f: dict) -> str:
    d = f"{f['primary']['code']} {f['primary']['name']}"
    if f.get("secondary"):
        d += f" / {f['secondary']['code']} {f['secondary']['name']}"
    if f.get("refinement"):
        d += f" · {f['refinement']}"
    return d


def _field_block(sess: dict) -> str:
    f = sess.get("field")
    if not f:
        return ("\n## Field\n\nNot yet classified — call `set_field` during "
                "discovery.")
    from . import knowledge
    out = f"\n## Field\n\n{_field_desc(f)} (classified by: {f['origin']})"
    entries = knowledge.entries_for(f["primary"]["code"], f.get("refinement"))
    if entries:
        out += "\n\n" + knowledge.format_entries(
            entries, "## Field playbook (accumulated across sessions — check "
                     "before re-deriving; contribute back at look-back)")
    return out


def build_system_prompt(sess: dict) -> str:
    t = sess["theorem"]
    parts = [
        "# Proof workspace",
        "",
        "You are the proof assistant inside an interactive proof workspace. "
        "A human mathematician is developing a proof step by step; you check "
        "their work, offer guidance, and take over only what they delegate. "
        "On your FIRST turn in this session, invoke the `prove-conjecture` "
        "skill and follow its disciplines throughout (counterexample search "
        "before proving, graded claims, discovery rationales, Lakatosian "
        "counterexample handling).",
        "",
        "## The statement under attack",
        "",
        f"Title: {t['title']}",
        f"Statement (LaTeX): {t['tex'] or '(none given)'}",
    ]
    if t.get("text") and t["text"] != t["tex"]:
        parts.append(f"Plain text: {t['text']}")
    ctx = _context_block(t)
    if ctx:
        parts += ["", ctx]
    parts.append(_field_block(sess))
    parts += [TOOL_PROTOCOL, MODE_CONTRACT, KB_CONTRACT]
    from .agent import theoremsearch_available
    from .lean import checker as _lean
    if theoremsearch_available():
        parts.append("\nThe `theorem_search` tool (TheoremSearch MCP) is "
                     "available this session — use it during discovery and "
                     "whenever a literature check would help (novelty gate, "
                     "verifying a recalled citation).")
    if _lean.available:
        parts.append(LEAN_PROTOCOL)
    if sess.get("demo"):
        parts.append(DEMO_LINE)
    return "\n".join(parts)


def state_recap(sess: dict) -> str:
    """Compact state summary injected when a fresh client couldn't resume
    the prior SDK conversation (server restart with stale session id)."""
    lines = ["[Context restore — the proof state so far, rebuilt from disk]",
             f"Session status: {sess['status']}"]
    if sess.get("field"):
        lines.append("Field: " + _field_desc(sess["field"]))
    if sess.get("kb_contributions"):
        lines.append(f"Knowledge-base contributions so far: "
                     f"{', '.join(sess['kb_contributions'])}")
    for st in sess["steps"]:
        lines.append(f"- {st['id']} ({st['kind']}, {st['author']}, "
                     f"{st['status']}): {st['statement_tex'][:200]}"
                     + (f" — {st['justification'][:120]}" if st['justification'] else ""))
        if st.get("agent_comment"):
            lines.append(f"    comment: {st['agent_comment'][:200]}")
    for cx in sess["counterexamples"]:
        lines.append(f"- counterexample {cx['id']} ({cx['diagnostic']}): "
                     f"{cx['description_tex'][:200]}")
    if sess["evidence"]:
        lines.append("Evidence log: " + "; ".join(
            f"{e['id']} {e['kind']}/{e['grade']}: {e['summary'][:100]}"
            for e in sess["evidence"][-8:]))
    lines.append("Saved scripts from earlier turns are still in your cwd — "
                 "re-run them as regression checks after any statement change.")
    return "\n".join(lines)


def _step_line(step: dict) -> str:
    just = f"\nJustification: {step['justification']}" if step["justification"] else \
           "\nJustification: (none given)"
    return (f"step {step['id']}:\nStatement: {step['statement_tex']}{just}")


def action_prompt(sess: dict, action: dict) -> str:
    kind = action["type"]
    if kind == "discover":
        edited = " (the human just EDITED the statement — prior context was cleared; redo it against the new statement)" \
            if action.get("edited") else ""
        return (f"The theorem statement was submitted{edited}. Run the "
                "discovery protocol: pin down the statement, classify the "
                "field with `set_field` (consult — or seed — the returned "
                "playbook), record the object definitions and the relevant "
                "results via the tools, and close with a short summary + "
                "suggested opening move. Do not start proving.")
    if kind == "check_step":
        step = next(s for s in sess["steps"] if s["id"] == action["step_id"])
        return (f"The human submitted a new proof {_step_line(step)}\n\n"
                "Check it in the context of the proof so far: is it correct, "
                "justified, and does it advance the argument? Verify with a "
                "script where the domain allows, log the evidence, then call "
                "`update_step` with the grade and a precise comment. If this "
                "step verifiably completes the whole proof (all steps "
                "verified, conclusion reached), run the skill's verification "
                "passes and call `set_status` with the write-up; a step that "
                "justifies an earlier partially_verified step may also "
                "upgrade that step's grade.")
    if kind == "hint":
        return ("The human asks for a hint toward the next step. One nudge, "
                "no spoilers, no state changes.")
    if kind == "suggest_next":
        return ("The human asks you to suggest the next step. Propose exactly "
                "one via `add_step` (leave it unverified) with a clear "
                "discovery_rationale, and explain briefly in prose.")
    if kind == "prove_subgoal":
        step = next(s for s in sess["steps"] if s["id"] == action["step_id"])
        return (f"The human delegates this subgoal to you — {_step_line(step)}\n\n"
                "Close it: explore, add the steps you need (as children via "
                "parent_id where natural), verify each, and update this "
                "step's grade when done.")
    if kind == "prove_remaining":
        return ("The human delegates the REST of the proof to you. Run the "
                "full prove-conjecture loop from the current state to an exit "
                "state (proved / refuted / partial). Add and grade steps as "
                "you go; finish with `set_status` and a write-up note.")
    if kind == "challenge":
        return ("The human asks you to CHALLENGE the conjecture: hunt for "
                "counterexamples against the statement and any shaky steps. "
                "Write and save search scripts (randomized, boundary, "
                "small-n exhaustive), log them as evidence. Report any hit "
                "with `report_counterexample` and the Lakatos diagnostic; "
                "if the hit definitively refutes the statement (machine-"
                "verified, no wiggle room), also call `set_status(refuted)` "
                "with the best revised conjecture in the note. Report an "
                "empty search honestly as supporting evidence only.")
    if kind == "formalize_step":
        step = next(s for s in sess["steps"] if s["id"] == action["step_id"])
        deps = [s for s in sess["steps"]
                if s.get("lean") and s["lean"]["check"] == "ok"
                and s["id"] != step["id"]]
        dep_note = ("Already-formalized steps you may build on: "
                    + ", ".join(f"{s['id']} (lemma {s['id']})" for s in deps)
                    + "."
                    if deps else "No dependencies are formalized yet.")
        return (f"The human asks you to FORMALIZE this {_step_line(step)}\n\n"
                f"{dep_note}\n\n"
                "Spawn the lean-formalizer subagent SYNCHRONOUSLY "
                "(run_in_background: false — a backgrounded subagent strands "
                "the job when your turn ends) with the statement, its "
                "justification, and the dependency lemmas' code (read their "
                "files under lean/ in your cwd if needed). Review the "
                "returned FAITHFULNESS critically, then call `set_lean` "
                f"(step_id='{step['id']}') with your own faithfulness note. "
                "Name the Lean declaration after the step id.")
    if kind == "assemble_lean":
        done = [s["id"] for s in sess["steps"]
                if s.get("lean") and s["lean"]["check"] == "ok"]
        todo = [s["id"] for s in sess["steps"]
                if s["status"] == "verified"
                and not (s.get("lean") and s["lean"]["check"] == "ok")]
        return ("The human asks you to GENERATE THE LEAN PROOF for the whole "
                "theorem from the proof so far. "
                + (f"Already formalized: {', '.join(done)}. " if done else "")
                + (f"First formalize the remaining verified steps "
                   f"({', '.join(todo)}) one at a time via the "
                   "lean-formalizer subagent, spawned SYNCHRONOUSLY "
                   "(run_in_background: false), reviewing faithfulness and "
                   "calling `set_lean` for each. "
                   if todo else "")
                + "Then assemble: one file proving the main theorem by "
                "chaining the step lemmas (their code is under lean/ in "
                "your cwd) — spawn the subagent for the assembly the same "
                "way, review the FINAL theorem statement's faithfulness "
                "against the session's theorem, and call `set_lean` with "
                "step_id='assembly'. If no step is verified yet, say what "
                "must be proved first and stop.")
    if kind == "generate_report":
        return ("The human asks for the FINAL PROOF REPORT. Read "
                "`../session.json` (relative to your cwd) for the complete "
                "record — steps with grades and evidence, discoveries, "
                "definitions, counterexamples, Lean code, chat. Then write "
                "the report narrative and call `set_report_narrative` with "
                "it. The narrative (markdown: ## headings, **bold**, $math$) "
                "should cover: the precise statement and its classification; "
                "the proof strategy and its key ideas; how the argument "
                "unfolded (including any gaps caught and repaired, or "
                "Lakatos events); what the executable checks established; "
                "how the Lean formalization corresponds to the informal "
                "proof (note any faithfulness subtleties); and relevant "
                "surrounding facts from the discovered context. END with a "
                "'## Provenance' section: per-step verification tier, which "
                "claims were machine-checked vs argued informally, and the "
                "consulted-vs-recalled status of every citation. Accuracy "
                "over flourish — describe only what the record supports. "
                "The mechanical sections (steps, context, Lean, transcript) "
                "are appended automatically; do NOT restate them verbatim.")
    if kind == "chat":
        return action.get("text", "")
    raise ValueError(f"unknown action type {kind!r}")
