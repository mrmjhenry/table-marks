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
from .store import ROOT


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
                "prove_remaining", "challenge", "chat"}


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


@app.post("/api/sessions")
async def sessions_create(request: Request):
    body = await request.json()
    mode = body.get("mode", "free")
    demo = body.get("demo")
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


@app.post("/api/sessions/{sid}/steps")
async def step_submit(sid: str, request: Request):
    """Human submits a proof step; an agent check turn is queued."""
    sess = _load_or_404(sid)
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
    ACTION_PHRASE = {
        "check_step": "re-check step {step_id}",
        "hint": "give me a hint",
        "suggest_next": "suggest the next step",
        "prove_subgoal": "take over subgoal {step_id}",
        "prove_remaining": "take over and prove the remaining",
        "challenge": "challenge the conjecture",
    }
    text = (body.get("text") or "").strip() or \
        ACTION_PHRASE[kind].format(step_id=body.get("step_id", "?"))
    store.add_chat(sess, "user", text, action=kind)
    store.save_session(sess)
    hub = get_hub(sid)
    hub.emit("state_patch", {"session": sess})
    hub.submit({k: v for k, v in body.items() if k in ("type", "step_id", "text")})
    return {"queued": True, "pending": hub.queue.qsize()}


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
