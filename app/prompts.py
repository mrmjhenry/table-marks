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
## Assistance modes

The action named in each user message defines how much you may take over:

- check_step — grade the human's step. Point out gaps precisely. Do NOT
  rewrite their proof or add your own steps; at most suggest what is
  missing in the agent_comment.
- hint — one nudge toward a productive next step. No full solutions, no
  spoilers, no state changes.
- suggest_next — propose exactly ONE next step via `add_step`, leave it
  unverified (the human will accept it by asking you to check it, or edit
  it). Explain your reasoning briefly in prose.
- prove_subgoal / prove_remaining — the human delegated this scope to you.
  Run the full prove-conjecture loop: explore, add steps, verify each,
  and finish with `set_status` if the whole proof reaches an exit state.
- challenge — counterexample hunt on the conjecture and current steps:
  randomized instances, boundary cases, small-n enumeration, saved as
  scripts. Report hits with `report_counterexample`; if the search comes
  up empty, log the search itself as evidence (grade: partially_verified).
- chat — answer the question. Use state tools only if the discussion
  genuinely changes the proof state.

Write prose for a mathematician: concise, honest about uncertainty, LaTeX
inside $...$ (the UI renders it with KaTeX).
"""

DEMO_LINE = """
## Teaching session

This is a guided walkthrough of a classical theorem for a user learning the
workspace. When a step is asserted without justification, grade it
partially_verified (or unverified) and explain the gap — do NOT silently
fill the gap yourself. Keep commentary encouraging and short.
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
    parts += [TOOL_PROTOCOL, MODE_CONTRACT]
    if sess.get("demo"):
        parts.append(DEMO_LINE)
    return "\n".join(parts)


def state_recap(sess: dict) -> str:
    """Compact state summary injected when a fresh client couldn't resume
    the prior SDK conversation (server restart with stale session id)."""
    lines = ["[Context restore — the proof state so far, rebuilt from disk]",
             f"Session status: {sess['status']}"]
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
    if kind == "check_step":
        step = next(s for s in sess["steps"] if s["id"] == action["step_id"])
        return (f"The human submitted a new proof {_step_line(step)}\n\n"
                "Check it in the context of the proof so far: is it correct, "
                "justified, and does it advance the argument? Verify with a "
                "script where the domain allows, log the evidence, then call "
                "`update_step` with the grade and a precise comment.")
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
    if kind == "chat":
        return action.get("text", "")
    raise ValueError(f"unknown action type {kind!r}")
