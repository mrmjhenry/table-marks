"""Session persistence and graph-context lookup for the proof workspace.

A proof session is one JSON file plus a scratch directory:

    sessions/<sid>/session.json   -- the full proof state (schema below)
    sessions/<sid>/workspace/     -- the agent's cwd: scripts, lean files

The session schema mirrors the prove-conjecture skill's model: graded steps,
an evidence log, Lakatos counterexample records, and a terminal status
(in_progress / proved / refuted / partial). All writes are atomic
(temp file + os.replace) so a crash never leaves a torn session.json.

GraphIndex wraps data/graph.json (the conjecture map's data) to snapshot a
node's theorem text plus its strongest neighbors and logical relations into
a new session -- the context the skill's Phase 0 asks for. The graph file is
optional: without it, free-form sessions still work.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSIONS_DIR = ROOT / "sessions"
GRAPH_PATH = ROOT / "data" / "graph.json"
DEMOS_DIR = ROOT / "app" / "demos"

STEP_STATUSES = {"verified", "partially_verified", "unverified", "refuted"}
SESSION_STATUSES = {"in_progress", "proved", "refuted", "partial"}
STEP_KINDS = {"step", "subgoal", "lemma", "case"}
EVIDENCE_KINDS = {"script", "computation", "citation", "counterexample", "lean", "note"}
DIAGNOSTICS = {"local_not_global", "global_and_local", "global_not_local"}
DISCOVERY_SOURCES = {"theoremsearch", "map", "recalled"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def derive_title(statement: str, limit: int = 70) -> str:
    """A readable session title from a raw theorem statement: prefer the
    prose, dropping $...$ math spans rather than mangling them."""
    import re
    t = statement.strip()
    t = re.sub(r"^\s*(prove|show|demonstrate)\s+that\s+", "", t, flags=re.I)
    def _math(m):        # keep simple math content (n, n^3-n), drop commands
        inner = re.sub(r"\\[a-zA-Z]+|[{}]", " ", m.group(1))
        return " " + re.sub(r"\s+", " ", inner).strip() + " "
    prose = re.sub(r"\$\$?([^$]*)\$\$?", _math, t)
    prose = re.sub(r"\\[a-zA-Z]+", " ", prose)           # stray commands
    prose = re.sub(r"\s+", " ", prose).strip(" \t:;,.-—")
    if len(prose) < 8:                                    # statement was mostly math
        prose = re.sub(r"[${}\\]", " ", t)
        prose = re.sub(r"\s+", " ", prose).strip()
    prose = prose or "Untitled conjecture"
    return prose if len(prose) <= limit else prose[:limit - 1].rstrip() + "…"


# ---------------------------------------------------------------- sessions

def new_session_id() -> str:
    return f"s_{datetime.now(timezone.utc):%Y%m%d}_{secrets.token_hex(3)}"


def session_dir(sid: str) -> Path:
    return SESSIONS_DIR / sid


def workspace_dir(sid: str) -> Path:
    return session_dir(sid) / "workspace"


def create_session(*, source_kind: str, node_id: str | None = None,
                   title: str | None = None, tex: str | None = None,
                   text: str | None = None, mode: str = "free",
                   demo: str | None = None) -> dict:
    """Create, persist, and return a new session.

    source_kind "map_node" pulls theorem + related-conjecture context from
    graph.json; "user" takes title/tex/text as given.
    """
    if source_kind == "map_node":
        g = get_graph()
        if g is None:
            raise ValueError("data/graph.json not available on this machine")
        theorem = g.node_context(node_id)
    else:
        theorem = {
            "title": (title or "Untitled conjecture").strip(),
            "tex": tex or "",
            "text": text or "",
            "context": None,
        }

    sess = {
        "id": new_session_id(),
        "created": now_iso(),
        "updated": now_iso(),
        "mode": mode,
        "demo": demo,
        "source": {"kind": source_kind, "node_id": node_id},
        "theorem": theorem,
        "status": "in_progress",
        "status_note": None,
        "steps": [],
        "discoveries": [],
        "definitions": [],
        "lean_assembly": None,
        "evidence": [],
        "counterexamples": [],
        "chat": [],
        "claude_session_id": None,
        "guided_cursor": 0,
        "counters": {"step": 0, "evidence": 0, "cx": 0, "turn": 0,
                     "disc": 0, "def": 0},
    }
    workspace_dir(sess["id"]).mkdir(parents=True, exist_ok=True)
    save_session(sess)
    return sess


def save_session(sess: dict) -> None:
    sess["updated"] = now_iso()
    path = session_dir(sess["id"]) / "session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(sess, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


def load_session(sid: str) -> dict | None:
    path = session_dir(sid) / "session.json"
    if not path.is_file():
        return None
    sess = json.loads(path.read_text())
    # backward compat: sessions created before the discovery feature
    sess.setdefault("discoveries", [])
    sess.setdefault("definitions", [])
    sess["counters"].setdefault("disc", 0)
    sess["counters"].setdefault("def", 0)
    return sess


def list_sessions() -> list[dict]:
    """Summaries of every session on disk, most recently updated first."""
    out = []
    if not SESSIONS_DIR.is_dir():
        return out
    for p in sorted(SESSIONS_DIR.glob("*/session.json")):
        try:
            s = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        out.append({
            "id": s["id"],
            "title": s["theorem"]["title"],
            "status": s["status"],
            "mode": s["mode"],
            "demo": s.get("demo"),
            "created": s["created"],
            "updated": s["updated"],
            "n_steps": len(s["steps"]),
        })
    out.sort(key=lambda s: s["updated"], reverse=True)
    return out


def delete_session(sid: str) -> bool:
    d = session_dir(sid)
    if not d.is_dir():
        return False
    import shutil
    shutil.rmtree(d)
    return True


# ------------------------------------------------- mutation helpers
# Used by both the HTTP layer (human-authored steps) and the agent's MCP
# tools. They mutate the session dict in place; callers save_session().

def _next_id(sess: dict, kind: str, prefix: str) -> str:
    sess["counters"][kind] += 1
    return f"{prefix}_{sess['counters'][kind]:03d}"


def add_step(sess: dict, *, statement_tex: str, justification: str = "",
             author: str = "human", kind: str = "step",
             discovery_rationale: str | None = None,
             parent_id: str | None = None) -> dict:
    if kind not in STEP_KINDS:
        raise ValueError(f"bad step kind {kind!r}")
    step = {
        "id": _next_id(sess, "step", "st"),
        "index": len(sess["steps"]) + 1,
        "kind": kind,
        "statement_tex": statement_tex,
        "justification": justification,
        "author": author,
        "status": "unverified",
        "agent_comment": None,
        "discovery_rationale": discovery_rationale,
        "evidence_ids": [],
        "parent_id": parent_id,
        "lean": None,
        "created": now_iso(),
        "updated": now_iso(),
    }
    sess["steps"].append(step)
    return step


def get_step(sess: dict, step_id: str) -> dict | None:
    return next((s for s in sess["steps"] if s["id"] == step_id), None)


def update_step(sess: dict, step_id: str, *, status: str,
                agent_comment: str | None = None,
                evidence_ids: list[str] | None = None) -> dict:
    if status not in STEP_STATUSES:
        raise ValueError(f"bad step status {status!r}")
    step = get_step(sess, step_id)
    if step is None:
        raise KeyError(f"no step {step_id}")
    step["status"] = status
    if agent_comment is not None:
        step["agent_comment"] = agent_comment
    if evidence_ids:
        step["evidence_ids"] = sorted(set(step["evidence_ids"]) | set(evidence_ids))
    step["updated"] = now_iso()
    return step


def add_evidence(sess: dict, *, kind: str, grade: str, summary: str,
                 script_path: str | None = None,
                 output_excerpt: str | None = None,
                 step_id: str | None = None) -> dict:
    if kind not in EVIDENCE_KINDS:
        raise ValueError(f"bad evidence kind {kind!r}")
    if grade not in STEP_STATUSES:
        raise ValueError(f"bad evidence grade {grade!r}")
    ev = {
        "id": _next_id(sess, "evidence", "ev"),
        "kind": kind,
        "grade": grade,
        "summary": summary,
        "script_path": script_path,
        "output_excerpt": output_excerpt,
        "step_id": step_id,
        "created": now_iso(),
    }
    sess["evidence"].append(ev)
    if step_id and (step := get_step(sess, step_id)):
        step["evidence_ids"].append(ev["id"])
    return ev


def add_counterexample(sess: dict, *, description_tex: str, diagnostic: str,
                       suggested_repair: str, repair_note: str = "",
                       guilty_step_id: str | None = None,
                       evidence_id: str | None = None) -> dict:
    if diagnostic not in DIAGNOSTICS:
        raise ValueError(f"bad diagnostic {diagnostic!r}")
    cx = {
        "id": _next_id(sess, "cx", "cx"),
        "description_tex": description_tex,
        "diagnostic": diagnostic,
        "guilty_step_id": guilty_step_id,
        "suggested_repair": suggested_repair,
        "repair_note": repair_note,
        "evidence_id": evidence_id,
        "created": now_iso(),
    }
    sess["counterexamples"].append(cx)
    return cx


def add_discovery(sess: dict, *, title: str, explanation: str, source: str,
                  tex: str | None = None) -> dict:
    if source not in DISCOVERY_SOURCES:
        raise ValueError(f"bad discovery source {source!r}")
    d = {"id": _next_id(sess, "disc", "d"), "title": title,
         "explanation": explanation, "source": source, "tex": tex,
         "created": now_iso()}
    sess["discoveries"].append(d)
    return d


def add_definition(sess: dict, *, term: str, definition: str) -> dict:
    d = {"id": _next_id(sess, "def", "df"), "term": term,
         "definition": definition, "created": now_iso()}
    sess["definitions"].append(d)
    return d


def clear_context(sess: dict) -> None:
    """Drop discoveries/definitions (theorem was edited; they'll be redone)."""
    sess["discoveries"] = []
    sess["definitions"] = []


def set_status(sess: dict, status: str, note: str | None = None) -> None:
    if status not in SESSION_STATUSES:
        raise ValueError(f"bad session status {status!r}")
    sess["status"] = status
    sess["status_note"] = note


def add_chat(sess: dict, role: str, text: str, *, action: str | None = None,
             turn_id: str | None = None) -> dict:
    msg = {"role": role, "text": text, "ts": now_iso()}
    if action:
        msg["action"] = action
    if turn_id:
        msg["turn_id"] = turn_id
    sess["chat"].append(msg)
    return msg


def next_turn_id(sess: dict) -> str:
    return _next_id(sess, "turn", "t")


# ---------------------------------------------------------------- graph

class GraphIndex:
    """In-memory indexes over data/graph.json for session-context snapshots."""

    def __init__(self, path: Path = GRAPH_PATH):
        g = json.loads(path.read_text())
        self.by_id = {n["id"]: n for n in g["nodes"]}
        # adjacency: node id -> [(other_id, weight, shared entities)]
        self.adj: dict[str, list] = {}
        for e in g["edges"]:
            self.adj.setdefault(e["s"], []).append((e["t"], e["w"], e["shared"]))
            self.adj.setdefault(e["t"], []).append((e["s"], e["w"], e["shared"]))
        # logical relations: node id -> [relation dict]
        self.rels: dict[str, list] = {}
        for r in g["relations"]:
            self.rels.setdefault(r["a"], []).append(r)
            self.rels.setdefault(r["b"], []).append(r)

    def node(self, node_id: str) -> dict | None:
        return self.by_id.get(node_id)

    def node_context(self, node_id: str, k: int = 8) -> dict:
        """Theorem record for a session, with top-k neighbors and relations."""
        n = self.by_id.get(node_id)
        if n is None:
            raise KeyError(f"unknown node id {node_id!r}")
        related = []
        for oid, w, shared in sorted(self.adj.get(node_id, []),
                                     key=lambda t: -t[1])[:k]:
            o = self.by_id[oid]
            related.append({"id": oid, "title": o["title"],
                            "tex": o.get("tex") or o.get("text") or "",
                            "shared": shared})
        relations = []
        for r in self.rels.get(node_id, []):
            oid = r["b"] if r["a"] == node_id else r["a"]
            o = self.by_id[oid]
            relations.append({"other_id": oid, "other_title": o["title"],
                              "rel": r["rel"], "why": r["why"]})
        return {
            "title": n["title"],
            "tex": n.get("tex") or "",
            "text": n.get("text") or "",
            "context": {
                "authors": n.get("authors", []),
                "cat": n.get("cat"),
                "msc": n.get("msc", []),
                "mscNames": n.get("mscNames", []),
                "url": n.get("url"),
                "related": related,
                "relations": relations,
            },
        }


_graph: GraphIndex | None = None
_graph_tried = False


def get_graph() -> GraphIndex | None:
    """Lazy singleton; None when data/graph.json is absent (fresh clone)."""
    global _graph, _graph_tried
    if not _graph_tried:
        _graph_tried = True
        if GRAPH_PATH.is_file():
            _graph = GraphIndex()
    return _graph
