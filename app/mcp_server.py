"""Standalone stdio MCP server exposing the proof-workspace capabilities
to Claude Code sessions in ANY project (via the math-prover plugin).

Run as:  PYTHONPATH=<repo> <repo>/.venv/bin/python -m app.mcp_server

Tools: MSC classification aids (msc_validate, msc_search), the shared field
knowledge base (query_knowledge, record_knowledge — same knowledge/ files
the workspace uses; CLI writes are attributed session_id "cli-YYYYMMDD"),
OpenConjecture similarity over the local embeddings (similar_conjectures,
conjecture_context), and Lean/Mathlib checking (lean_check).

Import discipline: top level pulls only FastMCP + stdlib + the stdlib-only
app modules (fields, knowledge), so initialize/tools-list is instant; the
graph, Lean checker, numpy, and sentence-transformers load lazily on first
use. No fastapi, no claude-agent-sdk. The `mcp` package itself arrives in
the venv as a claude-agent-sdk dependency — if the venv is ever rebuilt
minimal, `pip install mcp` restores this server.

Concurrency: knowledge writes share app/knowledge.py's stance — atomic
per-file replace, last-write-wins across processes (workspace server and
CLI sessions may both write; single-user localhost deployment).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import fields, knowledge

ROOT = Path(__file__).resolve().parent.parent

mcp = FastMCP("proof")

_emb = None      # lazy: (matrix, ids, model) for similar_conjectures


def _cli_session_id() -> str:
    return f"cli-{datetime.now(timezone.utc):%Y%m%d}"


# ------------------------------------------------------------- MSC aids

@mcp.tool()
def msc_validate(codes: list[str]) -> str:
    """Validate MSC 2020 codes against the official taxonomy (cap 2,
    order-preserving). Invalid five-char leaves fall back to their 3-char
    subclass, bare two-digit classes to NN-XX. Use before committing to a
    classification."""
    valid = fields.validate(codes)
    if not valid:
        return f"no valid MSC 2020 codes in {codes!r}"
    lines = [f"{c} — {fields.name_of(c)} ({fields.level(c)})" for c in valid]
    given = [str(c).strip().upper().replace(" ", "") for c in codes[:2]]
    fallbacks = [f"note: {g!r} is not an exact code; mapped to {v}"
                 for g, v in zip(given, valid) if g != v and g.replace("XX", "xx") != v]
    return "\n".join(lines + fallbacks)


@mcp.tool()
def msc_search(text: str, limit: int = 20) -> str:
    """Find MSC 2020 codes whose name contains the text (case-insensitive),
    or that start with a code prefix — use this to classify a mathematical
    statement down to the most specific leaf that genuinely fits."""
    t = text.strip().casefold()
    m = fields.msc()
    hits = [(c, n) for c, n in m.items()
            if t in n.casefold() or c.casefold().startswith(t)]
    if not hits:
        return f"no MSC 2020 entries match {text!r}"
    hits.sort(key=lambda x: x[0])
    out = [f"{c} — {n}" for c, n in hits[:limit]]
    if len(hits) > limit:
        out.append(f"… {len(hits) - limit} more matches (refine the search)")
    return "\n".join(out)


# ------------------------------------------------------ knowledge base

@mcp.tool()
def query_knowledge(code: str | None = None, query: str | None = None,
                    kind: str | None = None) -> str:
    """Look up the shared field knowledge base: give an MSC code (hierarchy-
    walked leaf → subclass → class) and/or a free-text query, optionally
    filtered by kind (technique, assumption, pitfall, lemma,
    counterexample_pattern, literature). Check the playbook before
    re-deriving a standard technique or lemma."""
    if not code and not query:
        return "give code and/or query"
    try:
        if query:
            entries = knowledge.search(query, code=code, kind=kind)
        else:
            entries = knowledge.entries_for(code)
            if kind:
                entries = [e for e in entries if e["kind"] == kind]
    except (ValueError, KeyError) as e:
        return f"{type(e).__name__}: {e}"
    head = "## Knowledge base" + (f" — {code} (walked leaf→subclass→class)"
                                  if code and not query else "")
    return knowledge.format_entries(entries, head)


@mcp.tool()
def record_knowledge(code: str, kind: str, title: str, body: str,
                     origin: str, refinement: str | None = None,
                     status: str | None = None,
                     entry_id: str | None = None) -> str:
    """Write to the persistent field knowledge base (shared with the proof
    workspace). kind: technique | assumption | pitfall | lemma |
    counterexample_pattern | literature. origin: 'session' for what THIS
    session actually established (look-back), 'seeded' for recalled
    playbook material (stays labeled unverified), 'theoremsearch' for
    durable literature hits. Pass entry_id to refine an existing entry
    instead of duplicating it. Writes are attributed to this CLI session
    (cli-YYYYMMDD)."""
    try:
        entry, created = knowledge.add_entry(
            code, kind=kind, title=title, body=body, origin=origin,
            session_id=_cli_session_id(), refinement=refinement,
            status=status, entry_id=entry_id)
    except (ValueError, KeyError) as e:
        return f"{type(e).__name__}: {e}"
    if not created and not entry_id:
        return (f"already known as {entry['id']} (“{entry['title']}”) — "
                "pass entry_id to refine it")
    verb = "recorded" if created else "refined"
    return (f"{verb} {entry['id']} in knowledge/"
            f"{knowledge.kb_file_code(entry['code'])}.json")


# ------------------------------------------------- OpenConjecture map

def _load_similarity():
    global _emb
    if _emb is None:
        import json as _json
        import numpy as np
        from sentence_transformers import SentenceTransformer
        emb_path = ROOT / "data" / "embeddings.npy"
        ids_path = ROOT / "data" / "embedding_ids.json"
        if not (emb_path.is_file() and ids_path.is_file()):
            raise FileNotFoundError(
                "data/embeddings.npy / embedding_ids.json not on this "
                "machine — similarity unavailable")
        _emb = (np.load(emb_path), _json.loads(ids_path.read_text()),
                SentenceTransformer("all-MiniLM-L6-v2"))
    return _emb


@mcp.tool()
def similar_conjectures(statement: str, k: int = 8) -> str:
    """Find the k most similar open conjectures in the OpenConjecture map
    (3,952 arXiv conjectures) for an arbitrary statement, by embedding
    similarity. NOTE: the first call in a session loads the embedding
    model (may download ~90 MB if uncached) and can take up to a minute;
    later calls are fast."""
    try:
        X, ids, model = _load_similarity()
    except Exception as e:
        return f"similarity unavailable: {e}"
    import numpy as np
    q = model.encode([statement.strip()[:1300]], normalize_embeddings=True)[0]
    sims = X @ q
    k = max(1, min(int(k), 25))
    top = np.argpartition(-sims, min(k, len(sims) - 1))[:k]
    top = top[np.argsort(-sims[top])]
    from . import store
    g = store.get_graph()
    lines = []
    for i in top:
        nid = ids[int(i)]
        n = g.by_id.get(nid) if g else None
        if n is None:
            lines.append(f"- {sims[i]:.2f} · {nid} (node detail unavailable)")
            continue
        stmt = (n.get("tex") or n.get("text") or "")[:300]
        meta = " · ".join(filter(None, [
            ", ".join(n.get("msc") or []) or None, n.get("cluster"),
            n.get("url")]))
        lines.append(f"- {sims[i]:.2f} · [{nid}] **{n['title']}** — {stmt}\n"
                     f"  {meta}")
    return ("## Nearest conjectures (cosine similarity)\n" + "\n".join(lines)
            + "\n\nUse conjecture_context(node_id) for a hit's neighbors "
              "and logical relations.")


@mcp.tool()
def conjecture_context(node_id: str) -> str:
    """Full OpenConjecture-map context for a conjecture node: statement,
    authors, MSC codes, its top-weighted neighbors with the shared
    mathematical objects, and any classified logical relations
    (implies / generalizes / equivalent / restates)."""
    from . import store
    g = store.get_graph()
    if g is None:
        return "data/graph.json not available on this machine"
    try:
        ctx = g.node_context(node_id)
    except KeyError:
        return f"unknown node id {node_id!r}"
    c = ctx["context"]
    out = [f"# {ctx['title']}",
           ctx.get("tex") or ctx.get("text") or "",
           " · ".join(filter(None, [
               c.get("cat"), ", ".join(c.get("msc") or []) or None,
               ", ".join((c.get("authors") or [])[:4]) or None,
               c.get("url")]))]
    if c.get("relations"):
        out.append("\n## Logical relations")
        for r in c["relations"]:
            out.append(f"- {r['rel']} “{r['other_title']}” "
                       f"[{r['other_id']}]: {r['why'][:250]}")
    if c.get("related"):
        out.append("\n## Most related conjectures (shared objects)")
        for r in c["related"]:
            out.append(f"- [{r['id']}] {r['title']} — shares: "
                       f"{', '.join(r['shared'][:6])}")
    return "\n".join(out)


# ---------------------------------------------------------------- lean

@mcp.tool()
async def lean_check(code: str) -> str:
    """Compile Lean 4 code against this machine's pinned Mathlib and return
    structured diagnostics (the hard oracle — Tier 4). Pure check, no LLM.
    Expect ~30 s minimum per compile (the `import Mathlib` load)."""
    from .lean import checker, lean_result_word
    if not checker.available:
        return ("Lean toolchain unavailable on this machine (elan/lake or "
                "the lean/ project missing) — skip Tier 4 and label "
                "accordingly.")
    res = await checker.check(code)
    word = lean_result_word(res)
    msgs = "\n".join(f"{e['severity']} L{e['line']}:{e['col']}: {e['message']}"
                     for e in res["errors"][:12])
    return (f"result: {word} ({res['sorries']} sorries, "
            f"{res['duration_s']}s)\n{msgs}").strip()


if __name__ == "__main__":
    mcp.run()
