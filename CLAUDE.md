# Project instructions

## Git

- **Never `git push`.** Committing locally is fine (and encouraged at natural
  checkpoints), but the user pushes to the remote manually themselves.
- Never commit: `sessions/`, `mockups/`, `data/`, `conjecture_map_local.html`,
  the CERME10 proceedings PDF (copyright). All but the PDF are gitignored.

## Running things

- Always use the project venv: `.venv/bin/python` / `.venv/bin/uvicorn`
  (system python lacks the deps; the pipeline's parquet also needs this venv's
  pyarrow).
- **Workspace server:** `uvicorn app.server:app --port 8765`. Routes: `/`
  workspace (also `/workspace`), `/openconjectures` map, `/api/*` JSON,
  `/api/sessions/{sid}/events` SSE.
- `PROOF_STUB_AGENT=1` swaps in a no-API stub agent — use it for all UI work
  and tests. `PROOF_AGENT_MODEL=claude-sonnet-5` keeps live agent tests fast
  and cheap.
- **UI testing:** headless Playwright (installed in the venv) against a stub
  server on a spare port. Drive the real page; don't unit-test the HTML.
  Screenshots catch rendering bugs (e.g. prose accidentally KaTeX-rendered)
  that DOM assertions miss.

## Architecture facts that bite

- **`conjecture_map.html` is generated.** Edit `templates/viz.html`, then run
  `.venv/bin/python scripts/05_render.py` (regenerates the published map and
  the gitignored `_local` variant). Never edit the output files.
- The published map must keep recovered arXiv text **redacted**
  (`04_graph.py` handles it; `src: "recovered"` nodes carry a placeholder).
  The unredacted variant is `conjecture_map_local.html` — gitignored, keep it
  that way.
- **Session writes are single-writer.** During an agent turn the runner owns
  the session dict and saves at turn end; direct-mutation endpoints return
  409 while busy, and user chat records are written by the worker at turn
  start. Don't add endpoints that write `session.json` without checking
  `hub.busy`.
- **Subagents must be spawned synchronously** (`run_in_background: false`).
  Claude Code's Task tool backgrounds them by default, which ends the main
  agent's turn and strands the job — the prompts in `app/prompts.py` enforce
  this; keep that language if editing them.
- **Bash sandbox is two-layer** (`app/agent.py`): a command allowlist (no
  chaining/substitution/redirection) plus macOS `sandbox-exec` write
  confinement to the session workspace. The allowlist alone cannot confine
  `python3 -c` — that's why the Seatbelt layer exists; don't remove it.
- **Lean checking** (`app/lean.py`) runs `lake env lean --json` against the
  pinned Mathlib in `lean/`; each compile costs ~30 s (the `import Mathlib`
  load). Feature-gated: without a toolchain the server hides all Lean UI and
  registers no Lean tools. The `λ machine-checked` badge requires a sorry-free
  compile AND affirmed statement-faithfulness — keep those coupled.
- The agent loads the `prove-conjecture` skill from `.claude/skills/` via
  `setting_sources=["project"]`; editing the skill changes workspace agent
  behavior with no code change. TheoremSearch is a remote MCP server
  (`https://api.theoremsearch.com/mcp`), reachability-probed at runner start.
- **The math-prover plugin** (`plugin/`) re-exposes these capabilities to
  Claude Code in any project via `app/mcp_server.py` (stdio, import-light —
  never add fastapi/SDK imports at its top level). After editing anything
  under `plugin/`, rerun `python3 plugin/install.py`. The project
  prove-conjecture skill is authoritative; mirror edits into
  `plugin/skills/prove-conjecture/` (minus its four repo-coupled prose
  spots). The workspace agent never loads plugins — `knowledge/` is the
  only surface shared between workspace and CLI.

## Costs

- Live agent turns spend real API money. Prefer the stub for iteration; use
  one short sonnet turn to validate agent-side changes, not full proofs.
- Pipeline stages (`scripts/`) are hash-keyed and resumable — safe to rerun;
  they skip completed work.
