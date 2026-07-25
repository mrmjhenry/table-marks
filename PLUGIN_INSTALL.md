# Installing the `math-prover` Claude Code plugin

The plugin brings this repo's theorem-proving capabilities into Claude Code
**in any project**: MSC field classification, the shared field knowledge
base, OpenConjecture similarity search, TheoremSearch, Lean/Mathlib
checking, and three skills (`prove-conjecture`, `math-context`,
`proof-report`) plus the `lean-formalizer` agent.

**The plugin is machine-bound by design.** Its MCP server runs from this
repo's virtualenv and reads this repo's local data. It is a personal
plugin, not a distributable — install it on the machine where this repo
lives.

## Prerequisites

| Requirement | Needed for | Notes |
|---|---|---|
| This repo cloned + `.venv` built | everything | `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` |
| Claude Code ≥ 2.1.2xx | everything | plugin auto-discovery via `~/.claude/skills/` |
| `data/` pipeline outputs | `similar_conjectures`, `conjecture_context` | **machine-local** (gitignored). Present if you ran the map pipeline (§ Reproducing in the README). Without them these two tools degrade gracefully; everything else works. |
| Lean toolchain (`brew install elan-init`; `cd lean && lake exe cache get`, ~5 GB) | `lean_check`, the `lean-formalizer` agent | optional; `lean_check` reports "toolchain unavailable" without it |
| Network access | `theorem_search` (remote MCP), first `similar_conjectures` call | the embedding model (~90 MB) downloads once to the HuggingFace cache |

No API key is needed by the plugin itself — its tools are local computations
plus the public TheoremSearch endpoint.

## Install (or update)

```bash
cd /path/to/this/repo
python3 plugin/install.py
```

This does two things:

1. Renders `plugin/.mcp.json` from the template, baking in this repo's
   absolute path (that file is gitignored — it's machine-specific).
2. Copies the plugin to `~/.claude/skills/math-prover/`, where Claude Code
   auto-discovers it as **`math-prover@skills-dir`** — user-wide, every
   project, every new session. No marketplace, no enable step.

**Rerun the same command after any edit under `plugin/`** (the installed
copy does not track the repo). Running Claude Code sessions pick changes up
on restart.

## Verify

```bash
claude plugin list          # expect: math-prover@skills-dir · loaded
```

Then, from any directory, in a Claude Code session:

- "Search MSC codes for 'arithmetic progressions'" → should call
  `msc_search` and surface `11B25`.
- "What does the knowledge base hold for 11Bxx?" → `query_knowledge`
  against this repo's `knowledge/`.
- "Find conjectures similar to: every planar graph is 4-colorable" →
  `similar_conjectures` (first call loads the model; up to ~1 min).
- `/math-prover:math-context` on any statement runs the full discovery
  protocol.

Headless (`claude -p`) sessions must allow the tools explicitly, e.g.
`--allowedTools "mcp__plugin_math-prover_proof"`.

## What gets installed

| Component | Name |
|---|---|
| Skills | `/math-prover:prove-conjecture`, `/math-prover:math-context`, `/math-prover:proof-report` (auto-trigger from their descriptions like any skill) |
| Agent | `lean-formalizer` (compile-fix loop against the pinned Mathlib) |
| MCP server `proof` (stdio, this repo's venv) | tools `msc_validate`, `msc_search`, `query_knowledge`, `record_knowledge`, `similar_conjectures`, `conjecture_context`, `lean_check` — fully-scoped ids `mcp__plugin_math-prover_proof__<tool>` |
| MCP server `theoremsearch` (remote) | tool `theorem_search` (semantic search over ~9M theorems) |

Knowledge-base writes from Claude Code sessions land in this repo's
`knowledge/` with provenance `cli-YYYYMMDD` — the same store the proof
workspace reads and writes, so what you learn in either surface benefits
both.

For the full end-to-end process this plugin supports (sign-off gates,
working modes, spoiler policy, Lean discipline, per-problem artifacts), see
**[PROOF_WORKFLOW.md](PROOF_WORKFLOW.md)**.

## Uninstall

```bash
rm -rf ~/.claude/skills/math-prover
```

## Troubleshooting

- **Tools missing in a session** — check `claude plugin list` shows
  `math-prover@skills-dir · loaded`; if you moved the repo, rerun
  `plugin/install.py` (the rendered `.mcp.json` bakes the old path).
- **`similar_conjectures` says "unavailable"** — `data/embeddings.npy` /
  `data/embedding_ids.json` are missing on this machine; run the map
  pipeline or accept the degradation.
- **`lean_check` says toolchain unavailable** — install elan and build
  `lean/` per the README's Lean section; the server looks for `lake` on a
  standard PATH (`/opt/homebrew/bin` included).
- **First similarity call is slow** — one-time model download/load; later
  calls are sub-second.
- **Plugin edits not taking effect** — rerun `plugin/install.py`, then
  restart the Claude Code session.
