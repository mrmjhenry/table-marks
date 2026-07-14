"""Claude Agent SDK runner for proof sessions.

One ProofRunner per active session holds a long-lived ClaudeSDKClient, so
the agent keeps its exploration state (examples computed, scripts written,
dead ends) across user actions. Structured proof-state updates come back
through an in-process MCP server ("proof") whose handlers mutate the live
session dict, persist it, and push a state_patch SSE event — grades are
never parsed out of prose.

Sandboxing: the built-in Bash/Write/Edit tools are gated by a can_use_tool
handler that confines writes to the session's workspace directory and Bash
to a conservative command shape (see _check_bash). The threat model is
agent error on a localhost single-user tool, not an adversary.

Restart durability: the SDK session id is persisted after every turn; a
fresh server resumes with it, and if resume fails the first prompt gets a
compact state recap rebuilt from session.json.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
import sys
import time
from pathlib import Path

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions,
                              ClaudeSDKClient, PermissionResultAllow,
                              PermissionResultDeny, ResultMessage,
                              StreamEvent, TextBlock, ToolUseBlock,
                              create_sdk_mcp_server, tool)

from . import prompts, store
from .lean import checker as lean_checker, lean_result_word
from .store import ROOT, now_iso

TURN_TIMEOUT = 15 * 60          # hard cap per agent turn (prove_remaining is long)
IDLE_TEARDOWN = 10 * 60         # disconnect a session's CLI subprocess after this
MAX_TURNS = 60

ALLOWED_TOOLS = [
    "Skill", "Read", "Grep", "Glob", "BashOutput", "KillShell",
    "mcp__proof__add_step", "mcp__proof__update_step",
    "mcp__proof__log_evidence", "mcp__proof__report_counterexample",
    "mcp__proof__set_status",
]
LEAN_TOOLS = ["mcp__proof__lean_check", "mcp__proof__set_lean",
              "Task"]        # Task: spawn the lean-formalizer subagent
DISALLOWED_TOOLS = ["WebFetch", "WebSearch", "TodoWrite",
                    "EnterPlanMode", "ExitPlanMode", "NotebookEdit"]


# ------------------------------------------------------------ permissions

SAFE_EXECUTABLES = {"python", "python3", "pip", "pip3", "ls", "cat", "head",
                    "tail", "wc", "grep", "echo", "pwd", "which", "true",
                    "diff", "sort", "uniq"}


def _unquoted_metachars(cmd: str) -> str | None:
    """Return the first shell metacharacter appearing outside quotes.

    Metachars inside quotes are fine (python3 -c "a; b" is one command);
    unquoted ones would chain/redirect and are rejected wholesale.
    """
    quote = None
    prev = ""
    for ch in cmd:
        if quote:
            if ch == quote and prev != "\\":
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch in ";|&<>":
            return ch
        prev = ch
    return None


def _check_bash(cmd: str, ws: Path) -> str | None:
    """Vet a Bash command; return a denial reason or None if allowed."""
    cmd = cmd.strip()
    if not cmd:
        return "empty command"
    if "`" in cmd or "$(" in cmd or "${" in cmd:
        return "command/variable substitution is not allowed"
    if (ch := _unquoted_metachars(cmd)) is not None:
        return (f"unquoted shell operator {ch!r} — run one simple command "
                "per Bash call (no chaining, pipes, or redirection; read "
                "output from the tool result instead)")
    exe = cmd.split()[0].rsplit("/", 1)[-1]
    if exe not in SAFE_EXECUTABLES:
        return (f"executable {exe!r} not in the allowlist "
                f"{sorted(SAFE_EXECUTABLES)}")
    if exe in ("pip", "pip3") and not re.match(r"pip3?\s+(install|show|list)\b", cmd):
        return "only `pip install/show/list` is allowed"
    # path discipline: no escapes; absolute paths must stay in the workspace
    for tok in cmd.split():
        bare = tok.strip("'\"")
        if bare.startswith("~") or ".." in bare:
            return f"path {bare!r} escapes the workspace — use relative paths"
        if bare.startswith("/"):
            try:
                ok = Path(bare).resolve().is_relative_to(ws.resolve())
            except OSError:
                ok = False
            if not ok:
                return (f"absolute path {bare!r} is outside your workspace "
                        f"({ws}) — use relative paths")
    return None


# macOS Seatbelt: the allowlist can't confine a Turing-complete `python3 -c`
# whose write path hides inside a string arg, so we ALSO run every approved
# Bash command under sandbox-exec with OS-enforced write confinement. Reads
# stay open (the allowlist handles read-path discipline); writes are limited
# to the session workspace plus the infra Python/pip genuinely need.
_SANDBOX_EXEC = shutil.which("sandbox-exec") if sys.platform == "darwin" else None


def _sandbox_profile(ws: Path) -> str:
    tmpdir = os.environ.get("TMPDIR", "/private/tmp").rstrip("/")
    writable = [str(ws.resolve()), str((ROOT / ".venv").resolve()),
                "/private/tmp", "/private/var/folders", tmpdir,
                str(Path.home() / "Library" / "Caches"),
                str(Path.home() / ".cache")]
    subpaths = "\n".join(f'(allow file-write* (subpath "{p}"))'
                         for p in dict.fromkeys(writable))
    return ("(version 1)\n(allow default)\n(deny file-write*)\n" + subpaths +
            '\n(allow file-write*'
            ' (literal "/dev/null") (literal "/dev/stdout")'
            ' (literal "/dev/stderr") (literal "/dev/dtracehelper")'
            ' (literal "/dev/tty"))\n')


def make_permission_handler(sid: str):
    """can_use_tool callback confining side effects to the session workspace."""
    ws = store.workspace_dir(sid)
    profile_path = None
    if _SANDBOX_EXEC:
        profile_path = ws.parent / "sandbox.sb"
        profile_path.write_text(_sandbox_profile(ws))

    async def handler(tool_name: str, tool_input: dict, context):
        if tool_name in ("Write", "Edit", "MultiEdit"):
            p = tool_input.get("file_path") or ""
            target = (ws / p) if not p.startswith("/") else Path(p)
            try:
                inside = target.resolve().is_relative_to(ws.resolve())
            except OSError:
                inside = False
            if inside:
                return PermissionResultAllow()
            return PermissionResultDeny(message=(
                f"You may only write inside your working directory {ws}. "
                "Use a relative path."))
        if tool_name == "Bash":
            cmd = tool_input.get("command", "")
            reason = _check_bash(cmd, ws)
            if reason is not None:
                return PermissionResultDeny(message="Denied: " + reason)
            with open(ws / "commands.log", "a") as f:
                f.write(cmd + "\n")
            if profile_path is not None:      # OS-enforce write confinement
                wrapped = (f"{shlex.quote(_SANDBOX_EXEC)} -f "
                           f"{shlex.quote(str(profile_path))} /bin/bash -c "
                           f"{shlex.quote(cmd)}")
                return PermissionResultAllow(updated_input={**tool_input,
                                                            "command": wrapped})
            return PermissionResultAllow()
        return PermissionResultDeny(message=(
            f"Tool {tool_name} is not available in the proof workspace."))

    return handler


# ------------------------------------------------------- proof MCP server

def _text(msg: str, is_error: bool = False) -> dict:
    out = {"content": [{"type": "text", "text": msg}]}
    if is_error:
        out["isError"] = True
    return out


def make_proof_server(runner: "ProofRunner"):
    """In-process MCP server whose handlers mutate the live session."""

    def sess() -> dict:
        if runner.current_sess is None:
            raise RuntimeError("no active turn")
        return runner.current_sess

    def commit():
        store.save_session(sess())
        if runner.current_hub:
            runner.current_hub.emit("state_patch", {"session": sess()})

    def guarded(fn):
        async def run(args):
            try:
                return fn(args)
            except (ValueError, KeyError, StopIteration, RuntimeError) as e:
                return _text(f"{type(e).__name__}: {e}", is_error=True)
        return run

    STATUS = {"enum": ["verified", "partially_verified", "unverified", "refuted"]}

    @tool("add_step",
          "Add a proof step you (the agent) author. Returns its step id.",
          {"type": "object",
           "properties": {
               "kind": {"enum": ["step", "subgoal", "lemma", "case"]},
               "statement_tex": {"type": "string"},
               "justification": {"type": "string"},
               "discovery_rationale": {"type": "string",
                                       "description": "why this step — no rabbits out of hats"},
               "parent_id": {"type": "string"}},
           "required": ["kind", "statement_tex", "justification",
                        "discovery_rationale"]})
    @guarded
    def add_step(a):
        if a.get("parent_id") and not store.get_step(sess(), a["parent_id"]):
            raise KeyError(f"no step {a['parent_id']}")
        st = store.add_step(sess(), statement_tex=a["statement_tex"],
                            justification=a["justification"], author="agent",
                            kind=a["kind"],
                            discovery_rationale=a["discovery_rationale"],
                            parent_id=a.get("parent_id"))
        commit()
        return _text(f"added {st['id']} (index {st['index']}, unverified)")

    @tool("update_step",
          "Grade a step (the ONLY way a grade counts) with an explanatory comment.",
          {"type": "object",
           "properties": {
               "step_id": {"type": "string"},
               "status": STATUS,
               "agent_comment": {"type": "string"},
               "evidence_ids": {"type": "array", "items": {"type": "string"}}},
           "required": ["step_id", "status", "agent_comment"]})
    @guarded
    def update_step(a):
        st = store.update_step(sess(), a["step_id"], status=a["status"],
                               agent_comment=a["agent_comment"],
                               evidence_ids=a.get("evidence_ids"))
        commit()
        return _text(f"{st['id']} -> {st['status']}")

    @tool("log_evidence",
          "Record a check you ran: script, computation, citation, counterexample, or note. "
          "Scripts must already be saved as files in your working directory.",
          {"type": "object",
           "properties": {
               "kind": {"enum": ["script", "computation", "citation",
                                 "counterexample", "note"]},
               "grade": STATUS,
               "summary": {"type": "string"},
               "script_path": {"type": "string",
                               "description": "path relative to your cwd"},
               "output_excerpt": {"type": "string"},
               "step_id": {"type": "string"}},
           "required": ["kind", "grade", "summary"]})
    @guarded
    def log_evidence(a):
        sp = a.get("script_path")
        if sp and not sp.startswith("workspace/"):
            sp = f"workspace/{sp}"        # file-viewer paths are session-relative
        if a.get("step_id") and not store.get_step(sess(), a["step_id"]):
            raise KeyError(f"no step {a['step_id']}")
        ev = store.add_evidence(sess(), kind=a["kind"], grade=a["grade"],
                                summary=a["summary"], script_path=sp,
                                output_excerpt=a.get("output_excerpt"),
                                step_id=a.get("step_id"))
        commit()
        return _text(f"logged {ev['id']}")

    @tool("report_counterexample",
          "Report a counterexample with its Lakatos diagnostic and a suggested repair.",
          {"type": "object",
           "properties": {
               "description_tex": {"type": "string"},
               "diagnostic": {"enum": ["local_not_global", "global_and_local",
                                       "global_not_local"]},
               "guilty_step_id": {"type": "string"},
               "suggested_repair": {"enum": ["lemma_incorporation",
                                             "exception_barring",
                                             "monster_barring", "surrender"]},
               "repair_note": {"type": "string"},
               "evidence_id": {"type": "string"}},
           "required": ["description_tex", "diagnostic", "suggested_repair",
                        "repair_note"]})
    @guarded
    def report_counterexample(a):
        cx = store.add_counterexample(
            sess(), description_tex=a["description_tex"],
            diagnostic=a["diagnostic"],
            suggested_repair=a["suggested_repair"],
            repair_note=a["repair_note"],
            guilty_step_id=a.get("guilty_step_id"),
            evidence_id=a.get("evidence_id"))
        commit()
        return _text(f"recorded {cx['id']} ({cx['diagnostic']})")

    @tool("set_status",
          "Set the session's terminal status with the mandated write-up note.",
          {"type": "object",
           "properties": {
               "status": {"enum": ["in_progress", "proved", "refuted", "partial"]},
               "note": {"type": "string",
                        "description": "final statement, method, evidence summary, "
                                       "machine-checked vs informal breakdown"}},
           "required": ["status", "note"]})
    @guarded
    def set_status(a):
        store.set_status(sess(), a["status"], a["note"])
        commit()
        return _text(f"session status -> {a['status']}")

    tools = [add_step, update_step, log_evidence, report_counterexample,
             set_status]

    if lean_checker.available:

        @tool("lean_check",
              "Compile Lean 4 code against the pinned Mathlib and return "
              "diagnostics. Pure check — does not touch the proof state. "
              "Iterate here until your code compiles.",
              {"type": "object",
               "properties": {"code": {"type": "string"}},
               "required": ["code"]})
        async def lean_check_tool(a):
            res = await lean_checker.check(a["code"])
            word = lean_result_word(res)
            msgs = "\n".join(f"{e['severity']} L{e['line']}:{e['col']}: {e['message']}"
                             for e in res["errors"][:12])
            return _text(f"result: {word} ({res['sorries']} sorries, "
                         f"{res['duration_s']}s)\n{msgs}".strip())

        @tool("set_lean",
              "Attach the FINAL Lean formalization to a step (or pass "
              "step_id='assembly' for the whole-proof file). Recompiles "
              "authoritatively, marks faithfulness affirmed by you — only "
              "call after genuinely reviewing that the formal statement "
              "matches the informal one.",
              {"type": "object",
               "properties": {
                   "step_id": {"type": "string",
                               "description": "a step id, or 'assembly'"},
                   "code": {"type": "string"},
                   "faithful_note": {"type": "string",
                                     "description": "why the formal statement is "
                                                    "faithful (quantifiers, hypotheses, "
                                                    "no trivialization)"}},
               "required": ["step_id", "code", "faithful_note"]})
        async def set_lean_tool(a):
            s = sess()
            target = a["step_id"]
            if target != "assembly" and not store.get_step(s, target):
                return _text(f"no step {target}", is_error=True)
            scratch = store.workspace_dir(runner.sid) / "lean" / f"{target}.lean"
            res = await lean_checker.check(a["code"], scratch_path=scratch)
            word = lean_result_word(res)
            rec = {"code": a["code"], "author": "agent", "check": word,
                   "sorries": res["sorries"], "errors": res["errors"],
                   "faithful": "affirmed_agent",
                   "faithful_note": a["faithful_note"],
                   "checked_at": now_iso()}
            if target == "assembly":
                s["lean_assembly"] = rec
            else:
                store.get_step(s, target)["lean"] = rec
            grade = {"ok": "verified", "has_sorries": "partially_verified",
                     "failed": "unverified"}[word]
            store.add_evidence(
                s, kind="lean", grade=grade,
                summary=f"Lean formalization of {target}: {word}, "
                        f"{res['sorries']} sorries",
                script_path=f"workspace/lean/{target}.lean",
                step_id=None if target == "assembly" else target)
            commit()
            msgs = "\n".join(f"{e['severity']} L{e['line']}: {e['message'][:200]}"
                             for e in res["errors"][:8])
            return _text(f"stored ({word})\n{msgs}".strip())

        tools += [lean_check_tool, set_lean_tool]

    return create_sdk_mcp_server(name="proof", tools=tools)


# ---------------------------------------------------------------- runner

def _tool_detail(block: ToolUseBlock) -> str:
    i = block.input or {}
    if block.name == "Bash":
        return (i.get("command") or "")[:100]
    if block.name in ("Write", "Edit", "Read"):
        return (i.get("file_path") or "")[-60:]
    if block.name == "Skill":
        return i.get("skill") or i.get("command") or ""
    if block.name.startswith("mcp__proof__"):
        return " ".join(str(i.get(k)) for k in ("step_id", "status", "kind")
                        if i.get(k))
    return ""


class ProofRunner:
    """Owns the SDK client + MCP server for one proof session."""

    def __init__(self, sid: str):
        self.sid = sid
        self.client: ClaudeSDKClient | None = None
        self.mcp = make_proof_server(self)
        self.current_sess: dict | None = None
        self.current_hub = None
        self.last_used = time.monotonic()
        self.fresh_resume = False     # resumed this process, no completed turn yet
        self.needs_recap = False

    def _options(self, sess: dict, resume: str | None) -> ClaudeAgentOptions:
        import os
        ws = store.workspace_dir(self.sid)
        env = {"PATH": f"{ROOT / '.venv' / 'bin'}:{os.environ.get('PATH', '')}"}
        return ClaudeAgentOptions(
            cwd=str(ws),
            setting_sources=["project"],
            skills=["prove-conjecture"],
            system_prompt={"type": "preset", "preset": "claude_code",
                           "append": prompts.build_system_prompt(sess)},
            resume=resume,
            mcp_servers={"proof": self.mcp},
            allowed_tools=ALLOWED_TOOLS + (LEAN_TOOLS if lean_checker.available else []),
            disallowed_tools=DISALLOWED_TOOLS + ([] if lean_checker.available else ["Task"]),
            can_use_tool=make_permission_handler(self.sid),
            max_turns=MAX_TURNS,
            include_partial_messages=True,
            model=os.environ.get("PROOF_AGENT_MODEL") or None,
            env=env,
        )

    async def _connect(self, sess: dict, resume: str | None) -> None:
        self.client = ClaudeSDKClient(options=self._options(sess, resume))
        await self.client.connect()
        self.fresh_resume = resume is not None
        self.needs_recap = resume is None and bool(sess["steps"] or sess["chat"])

    async def _ensure_client(self, sess: dict) -> None:
        if self.client is not None:
            return
        resume = sess.get("claude_session_id")
        try:
            await self._connect(sess, resume)
        except Exception:
            if resume is None:
                raise
            await self._connect(sess, None)   # stale id — fresh conversation

    async def _reset_client(self, sess: dict) -> None:
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.client = None
        await self._connect(sess, None)

    async def run_turn(self, sess: dict, action: dict, turn_id: str, hub) -> None:
        self.last_used = time.monotonic()
        self.current_sess, self.current_hub = sess, hub
        try:
            await self._ensure_client(sess)
            prompt = prompts.action_prompt(sess, action)
            if self.needs_recap:
                prompt = prompts.state_recap(sess) + "\n\n" + prompt
                self.needs_recap = False
            try:
                await self._stream_turn(sess, prompt, turn_id, hub)
            except Exception:
                if not self.fresh_resume:
                    raise
                # resume looked fine at connect but died on first use —
                # rebuild without it and replay this action once, with recap
                await self._reset_client(sess)
                prompt = prompts.state_recap(sess) + "\n\n" + \
                    prompts.action_prompt(sess, action)
                self.needs_recap = False
                await self._stream_turn(sess, prompt, turn_id, hub)
        finally:
            self.current_sess = self.current_hub = None
            self.last_used = time.monotonic()

    async def _stream_turn(self, sess: dict, prompt: str, turn_id: str, hub) -> None:
        await self.client.query(prompt)
        prose: list[str] = []
        try:
            async with asyncio.timeout(TURN_TIMEOUT):
                async for msg in self.client.receive_response():
                    if isinstance(msg, StreamEvent):
                        ev = msg.event
                        if (ev.get("type") == "content_block_delta"
                                and ev.get("delta", {}).get("type") == "text_delta"
                                and msg.parent_tool_use_id is None):
                            hub.emit("agent_text",
                                     {"turn_id": turn_id,
                                      "text": ev["delta"]["text"]})
                    elif isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock) and block.text.strip():
                                prose.append(block.text)
                            elif isinstance(block, ToolUseBlock):
                                hub.emit("tool_activity",
                                         {"tool": block.name.removeprefix("mcp__proof__"),
                                          "detail": _tool_detail(block)})
                    elif isinstance(msg, ResultMessage):
                        sess["claude_session_id"] = msg.session_id
                        self.fresh_resume = False
                        if msg.is_error:
                            hub.emit("error", {"message": msg.result or msg.subtype})
        except TimeoutError:
            await self.interrupt()
            hub.emit("error", {"message": f"turn exceeded {TURN_TIMEOUT}s and was interrupted"})
        final = "\n\n".join(prose).strip()
        if final:
            store.add_chat(sess, "agent", final, turn_id=turn_id)
        store.save_session(sess)
        hub.emit("state_patch", {"session": sess})

    async def interrupt(self) -> None:
        if self.client:
            try:
                await self.client.interrupt()
            except Exception:
                pass

    async def close(self) -> None:
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.client = None


class AgentManager:
    """Registry of ProofRunners + idle reaper. Drop-in for the stub."""

    def __init__(self):
        self.runners: dict[str, ProofRunner] = {}

    def _runner(self, sid: str) -> ProofRunner:
        if sid not in self.runners:
            self.runners[sid] = ProofRunner(sid)
        return self.runners[sid]

    async def run_turn(self, sess: dict, action: dict, turn_id: str, hub) -> None:
        await self._runner(sess["id"]).run_turn(sess, action, turn_id, hub)

    async def interrupt(self, sid: str) -> None:
        if sid in self.runners:
            await self.runners[sid].interrupt()

    async def reap_idle_forever(self) -> None:
        while True:
            await asyncio.sleep(60)
            now = time.monotonic()
            for r in list(self.runners.values()):
                if (r.client is not None and r.current_sess is None
                        and now - r.last_used > IDLE_TEARDOWN):
                    await r.close()

    async def close_all(self) -> None:
        for r in self.runners.values():
            await r.close()
        self.runners.clear()
