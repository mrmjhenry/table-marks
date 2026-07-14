"""FastAPI server for the proof workspace.

    uvicorn app.server:app --port 8765

Serves the existing conjecture map, the workspace page, and a JSON API.
Browser -> server is plain fetch POSTs; server -> browser is one SSE stream
per session (event types: turn_started, agent_text, state_patch,
tool_activity, turn_done, error). Each session has a Hub holding an action
queue drained by a single worker task, so at most one agent turn runs per
session at a time.

The agent itself is pluggable: agent.py provides the real Claude Agent SDK
runner; until it lands, a stub echoes canned turns so the UI and SSE
plumbing can be exercised end to end.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (FileResponse, JSONResponse, PlainTextResponse,
                               StreamingResponse)
from fastapi.staticfiles import StaticFiles

from . import store
from .lean import checker as lean_checker, lean_result_word
from .store import ROOT, now_iso


@contextlib.asynccontextmanager
async def lifespan(app):
    reaper = None
    if hasattr(agent_runner, "reap_idle_forever"):
        reaper = asyncio.create_task(agent_runner.reap_idle_forever())
    yield
    if reaper:
        reaper.cancel()
    if hasattr(agent_runner, "close_all"):
        await agent_runner.close_all()


app = FastAPI(title="proof-workspace", docs_url=None, redoc_url=None,
              lifespan=lifespan)

ACTION_TYPES = {"check_step", "hint", "suggest_next", "prove_subgoal",
                "prove_remaining", "challenge", "chat",
                "formalize_step", "assemble_lean"}


# ------------------------------------------------------------------ hubs

class Hub:
    """Per-session runtime: action queue, worker task, SSE subscribers."""

    def __init__(self, sid: str):
        self.sid = sid
        self.queue: asyncio.Queue = asyncio.Queue()
        self.subs: list[asyncio.Queue] = []
        self.worker: asyncio.Task | None = None
        self.busy = False

    def emit(self, event: str, data: dict) -> None:
        for q in list(self.subs):
            q.put_nowait({"event": event, "data": data})

    def submit(self, action: dict) -> None:
        self.queue.put_nowait(action)
        self.ensure_worker()

    def ensure_worker(self) -> None:
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self._run())

    async def interrupt(self) -> None:
        await agent_runner.interrupt(self.sid)

    async def _run(self) -> None:
        while True:
            action = await self.queue.get()
            sess = store.load_session(self.sid)
            if sess is None:      # deleted while queued
                continue
            self.busy = True
            # user-visible record of what was asked, written HERE (the
            # worker owns the session during a turn — writing it at submit
            # time would race with a running turn's save)
            if action.get("_chat"):
                store.add_chat(sess, "user", action.pop("_chat"),
                               action=action["type"])
                store.save_session(sess)
                self.emit("state_patch", {"session": sess})
            turn_id = store.next_turn_id(sess)
            self.emit("turn_started", {"turn_id": turn_id,
                                       "action": action["type"]})
            try:
                await agent_runner.run_turn(sess, action, turn_id, self)
            except Exception as e:  # surface, don't kill the worker
                self.emit("error", {"message": f"{type(e).__name__}: {e}"})
                store.save_session(sess)
                self.emit("state_patch", {"session": sess})
            finally:
                self.busy = False
                self.emit("turn_done", {"turn_id": turn_id})


_hubs: dict[str, Hub] = {}


def get_hub(sid: str) -> Hub:
    if sid not in _hubs:
        _hubs[sid] = Hub(sid)
    return _hubs[sid]


# ------------------------------------------------------------ stub agent

class StubAgent:
    """Placeholder runner: streams canned prose and grades steps as
    unverified, exercising the full SSE/state_patch path. Replaced by the
    real Claude Agent SDK runner in agent.py (plan step 4)."""

    async def run_turn(self, sess: dict, action: dict, turn_id: str,
                       hub: Hub) -> None:
        kind = action["type"]
        if kind == "check_step":
            step = store.get_step(sess, action.get("step_id", ""))
            text = (f"[stub] I would now check step {step['id']} with the "
                    "prove-conjecture skill. The real agent lands in step 4."
                    if step else "[stub] no such step.")
        else:
            text = f"[stub] action '{kind}' acknowledged — real agent lands in step 4."

        for word in text.split(" "):          # simulate token streaming
            hub.emit("agent_text", {"turn_id": turn_id, "text": word + " "})
            await asyncio.sleep(0.02)

        if kind == "check_step" and (step := store.get_step(sess, action.get("step_id", ""))):
            ev = store.add_evidence(sess, kind="note", grade="unverified",
                                    summary="stub check — no real verification performed",
                                    step_id=step["id"])
            store.update_step(sess, step["id"], status="unverified",
                              agent_comment="Stub grading: awaiting real agent (step 4).",
                              evidence_ids=[ev["id"]])

        store.add_chat(sess, "agent", text, turn_id=turn_id)
        store.save_session(sess)
        hub.emit("state_patch", {"session": sess})

    async def interrupt(self, sid: str) -> None:
        pass


if os.environ.get("PROOF_STUB_AGENT"):
    agent_runner = StubAgent()          # UI tests without an API key / spend
else:
    from .agent import AgentManager
    agent_runner = AgentManager()


# ---------------------------------------------------------------- pages

@app.get("/")
def map_page():
    for name in ("conjecture_map_local.html", "conjecture_map.html"):
        p = ROOT / name
        if p.is_file():
            return FileResponse(p, media_type="text/html")
    raise HTTPException(404, "no conjecture map html found — run scripts/05_render.py")


@app.get("/workspace")
def workspace_page():
    p = ROOT / "app" / "static" / "workspace.html"
    if p.is_file():
        return FileResponse(p, media_type="text/html")
    return PlainTextResponse("workspace page lands in step 3")


app.mount("/vendor/katex", StaticFiles(directory=ROOT / "vendor" / "katex"),
          name="katex")


# ------------------------------------------------------------------ api

@app.get("/api/health")
def health():
    # CORS * on this route only: the map probes it from file:// origins.
    return JSONResponse({"ok": True, "app": "proof-workspace", "version": "0.1"},
                        headers={"Access-Control-Allow-Origin": "*"})


@app.get("/api/sessions")
def sessions_list():
    return store.list_sessions()


def _load_demo(name: str) -> dict:
    if not name or not name.replace("_", "").isalnum():
        raise HTTPException(400, f"bad demo name {name!r}")
    p = ROOT / "app" / "demos" / f"{name}.json"
    if not p.is_file():
        raise HTTPException(404, f"no demo {name!r}")
    return json.loads(p.read_text())


@app.get("/api/demos/{name}")
def demo_get(name: str):
    return _load_demo(name)


@app.post("/api/sessions")
async def sessions_create(request: Request):
    body = await request.json()
    mode = body.get("mode", "free")
    demo = body.get("demo")
    if demo:
        d = _load_demo(demo)
        sess = store.create_session(source_kind="user",
                                    title=d["theorem"]["title"],
                                    tex=d["theorem"]["tex"],
                                    text=d["theorem"].get("text"),
                                    mode="guided", demo=demo)
        return sess
    try:
        if body.get("node_id"):
            sess = store.create_session(source_kind="map_node",
                                        node_id=body["node_id"],
                                        mode=mode, demo=demo)
        else:
            if not (body.get("title") or body.get("tex") or body.get("text")):
                raise ValueError("give node_id, or a title/tex/text")
            sess = store.create_session(source_kind="user",
                                        title=body.get("title"),
                                        tex=body.get("tex"),
                                        text=body.get("text"),
                                        mode=mode, demo=demo)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))
    return sess


def _load_or_404(sid: str) -> dict:
    sess = store.load_session(sid)
    if sess is None:
        raise HTTPException(404, f"no session {sid}")
    return sess


@app.get("/api/sessions/{sid}")
def session_get(sid: str):
    sess = _load_or_404(sid)
    sess["busy"] = get_hub(sid).busy      # transient, not persisted
    return sess


@app.delete("/api/sessions/{sid}")
def session_delete(sid: str):
    _load_or_404(sid)
    hub = _hubs.pop(sid, None)
    if hub and hub.worker:
        hub.worker.cancel()
    store.delete_session(sid)
    return {"deleted": sid}


def _reject_if_busy(sid: str) -> None:
    """Direct-mutation endpoints must not race a running agent turn: the
    runner saves its own session dict at turn end and would clobber us."""
    if get_hub(sid).busy:
        raise HTTPException(409, "an agent turn is running — try again when it finishes")


@app.post("/api/sessions/{sid}/steps")
async def step_submit(sid: str, request: Request):
    """Human submits a proof step; an agent check turn is queued."""
    sess = _load_or_404(sid)
    _reject_if_busy(sid)
    body = await request.json()
    statement = (body.get("statement") or "").strip()
    if not statement:
        raise HTTPException(400, "statement required")
    step = store.add_step(sess, statement_tex=statement,
                          justification=(body.get("justification") or "").strip(),
                          author="human")
    store.add_chat(sess, "user", statement, action="add_step")
    store.save_session(sess)
    hub = get_hub(sid)
    hub.emit("state_patch", {"session": sess})
    hub.submit({"type": "check_step", "step_id": step["id"]})
    return {"step_id": step["id"], "queued": True}


@app.post("/api/sessions/{sid}/actions")
async def action_submit(sid: str, request: Request):
    sess = _load_or_404(sid)
    body = await request.json()
    kind = body.get("type")
    if kind not in ACTION_TYPES:
        raise HTTPException(400, f"unknown action type {kind!r}")
    if kind in ("check_step", "prove_subgoal") and not store.get_step(sess, body.get("step_id", "")):
        raise HTTPException(400, f"no step {body.get('step_id')!r}")
    if kind == "chat" and not (body.get("text") or "").strip():
        raise HTTPException(400, "chat needs text")
    if kind in ("formalize_step", "assemble_lean") and not lean_checker.available:
        raise HTTPException(400, "Lean toolchain not installed on this machine")
    ACTION_PHRASE = {
        "check_step": "re-check step {step_id}",
        "hint": "give me a hint",
        "suggest_next": "suggest the next step",
        "prove_subgoal": "take over subgoal {step_id}",
        "prove_remaining": "take over and prove the remaining",
        "challenge": "challenge the conjecture",
        "formalize_step": "formalize step {step_id} in Lean",
        "assemble_lean": "assemble the full Lean proof",
    }
    text = (body.get("text") or "").strip() or \
        ACTION_PHRASE[kind].format(step_id=body.get("step_id", "?"))
    hub = get_hub(sid)
    action = {k: v for k, v in body.items() if k in ("type", "step_id", "text")}
    action["_chat"] = text          # recorded by the worker at turn start
    hub.submit(action)
    return {"queued": True, "pending": hub.queue.qsize()}


@app.get("/api/lean/status")
def lean_status():
    return {"available": lean_checker.available,
            "toolchain": lean_checker.toolchain,
            "mathlib_rev": lean_checker.mathlib_rev}


def _lean_record(code: str, res: dict, author: str) -> dict:
    return {"code": code, "author": author,
            "check": lean_result_word(res), "sorries": res["sorries"],
            "errors": res["errors"], "faithful": "unreviewed",
            "checked_at": now_iso()}


EVIDENCE_GRADE = {"ok": "verified", "has_sorries": "partially_verified",
                  "failed": "unverified"}


@app.post("/api/sessions/{sid}/lean/check")
async def lean_check_user(sid: str, request: Request):
    """User-provided Lean: pure compiler round-trip, no agent involved."""
    sess = _load_or_404(sid)
    _reject_if_busy(sid)
    if not lean_checker.available:
        raise HTTPException(400, "Lean toolchain not installed on this machine")
    body = await request.json()
    code = (body.get("code") or "").strip()
    if not code:
        raise HTTPException(400, "code required")
    step_id = body.get("step_id")
    target = "assembly" if body.get("assembly") else step_id
    if target != "assembly" and not store.get_step(sess, step_id or ""):
        raise HTTPException(400, f"no step {step_id!r}")

    scratch = store.workspace_dir(sid) / "lean" / f"{target}.lean"
    res = await lean_checker.check(code, scratch_path=scratch)
    rec = _lean_record(code, res, "human")
    word = rec["check"]
    if target == "assembly":
        sess["lean_assembly"] = rec
        label = "assembled proof"
    else:
        store.get_step(sess, step_id)["lean"] = rec
        label = f"step {step_id}"
    store.add_evidence(sess, kind="lean", grade=EVIDENCE_GRADE[word],
                       summary=f"Lean check of {label} (human-provided): {word}, "
                               f"{res['sorries']} sorries, "
                               f"{sum(1 for e in res['errors'] if e['severity']=='error')} errors",
                       script_path=f"workspace/lean/{target}.lean",
                       step_id=None if target == "assembly" else step_id)
    store.save_session(sess)
    get_hub(sid).emit("state_patch", {"session": sess})
    return {"check": word, **res}


@app.post("/api/sessions/{sid}/lean/affirm")
async def lean_affirm(sid: str, request: Request):
    """Human confirms the formal statement matches the informal step."""
    sess = _load_or_404(sid)
    _reject_if_busy(sid)
    body = await request.json()
    if body.get("assembly"):
        rec = sess.get("lean_assembly")
    else:
        step = store.get_step(sess, body.get("step_id", ""))
        rec = step and step.get("lean")
    if not rec:
        raise HTTPException(400, "nothing formalized there yet")
    if rec["check"] != "ok":
        raise HTTPException(400, "only a clean compile can be affirmed")
    rec["faithful"] = "affirmed_human"
    store.save_session(sess)
    get_hub(sid).emit("state_patch", {"session": sess})
    return {"faithful": "affirmed_human"}


@app.post("/api/sessions/{sid}/guided")
async def guided_cursor(sid: str, request: Request):
    """Persist guided-demo progress so a reload resumes the walkthrough."""
    sess = _load_or_404(sid)
    _reject_if_busy(sid)
    body = await request.json()
    cur = body.get("cursor")
    if not isinstance(cur, int) or cur < 0:
        raise HTTPException(400, "cursor must be a non-negative integer")
    sess["guided_cursor"] = cur
    store.save_session(sess)
    return {"cursor": cur}


@app.post("/api/sessions/{sid}/interrupt")
async def session_interrupt(sid: str):
    _load_or_404(sid)
    await get_hub(sid).interrupt()
    return {"interrupted": True}


@app.get("/api/sessions/{sid}/events")
async def session_events(sid: str):
    _load_or_404(sid)
    hub = get_hub(sid)
    q: asyncio.Queue = asyncio.Queue()
    hub.subs.append(q)

    async def gen():
        try:
            yield "retry: 2000\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"event: {ev['event']}\ndata: {json.dumps(ev['data'])}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"        # keepalive
        finally:
            if q in hub.subs:
                hub.subs.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@app.get("/api/sessions/{sid}/files/{path:path}")
def session_file(sid: str, path: str):
    """Read-only viewer for scripts the agent saved in the session dir."""
    _load_or_404(sid)
    base = store.session_dir(sid).resolve()
    target = (base / path).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise HTTPException(404, "no such file")
    return PlainTextResponse(target.read_text(errors="replace"))
