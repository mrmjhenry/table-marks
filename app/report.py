"""Build the final proof report: one self-contained HTML file.

The agent contributes only the narrative (via the set_report_narrative MCP
tool); everything else — the graded proof, the discovered context, the Lean
code, and the chat transcript — is assembled deterministically from the
session record, so the report cannot misquote what actually happened.

The file embeds the vendored KaTeX (CSS with inlined fonts + JS), matching
the conjecture map's zero-external-requests ethos: the report is a single
shareable file that renders math offline.
"""

from __future__ import annotations

import html
import re

from .store import ROOT, workspace_dir

KATEX_CSS = ROOT / "vendor" / "katex" / "katex.inline.css"
KATEX_JS = ROOT / "vendor" / "katex" / "katex.bundle.js"

GRADE_COLOR = {"verified": "#1baf7a", "partially_verified": "#eda100",
               "unverified": "#898781", "refuted": "#e34948"}
SOURCE_LABEL = {"theoremsearch": "TheoremSearch", "map": "conjecture map",
                "recalled": "recalled"}

CSS = """
:root { --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --grid:#e1e0d9;
        --border:rgba(11,11,11,.12); --bg:#fcfcfb; --accent:#2a78d6; }
* { box-sizing:border-box; margin:0; }
body { font:15px/1.65 Georgia, 'Times New Roman', serif; color:var(--ink);
       background:var(--bg); }
.wrap { max-width:860px; margin:0 auto; padding:48px 28px 80px; }
h1 { font-size:26px; line-height:1.3; margin-bottom:6px; }
h2 { font-size:19px; margin:36px 0 12px; border-bottom:1px solid var(--grid);
     padding-bottom:6px; }
h3 { font-size:16px; margin:20px 0 8px; }
p { margin:10px 0; }
.meta { font:13px system-ui, sans-serif; color:var(--muted); margin-bottom:22px; }
.badge { display:inline-block; font:600 10.5px system-ui, sans-serif;
         text-transform:uppercase; letter-spacing:.4px; padding:1px 9px;
         border-radius:10px; border:1.5px solid; vertical-align:middle; }
.stmt { font-size:17px; border-left:3px solid var(--accent); padding:6px 0 6px 16px;
        margin:14px 0 6px; }
.step { border:1px solid var(--border); border-radius:10px; padding:12px 16px;
        margin:12px 0; background:#fff; }
.step .top { font:12px system-ui, sans-serif; color:var(--muted); margin-bottom:6px;
             display:flex; gap:10px; align-items:baseline; flex-wrap:wrap; }
.step .just, .step .why { font-size:13.5px; color:var(--ink2); margin-top:5px; }
.step .comment { font-size:13.5px; color:var(--ink2); margin-top:7px;
                 border-left:2.5px solid var(--grid); padding-left:12px; }
.ev { font:13px system-ui, sans-serif; color:var(--ink2); border-bottom:1px solid var(--grid);
      padding:7px 0; }
.ev code, .lean pre code { font:12px ui-monospace, Menlo, monospace; }
.chip { display:inline-block; font:600 10px system-ui, sans-serif; padding:1px 8px;
        border-radius:9px; background:var(--grid); color:var(--ink2); }
.dItem { padding:10px 0; border-bottom:1px solid var(--grid); }
.dItem .t { font-weight:700; }
.dItem .x { font-size:14px; color:var(--ink2); }
.lean pre { background:#f4f4f1; border:1px solid var(--grid); border-radius:10px;
            padding:14px 16px; overflow-x:auto; margin:10px 0; }
.chat { font-size:14px; }
.chat .m { border-radius:10px; padding:10px 14px; margin:10px 0; max-width:92%; }
.chat .u { background:var(--grid); margin-left:auto; }
.chat .a { background:#fff; border:1px solid var(--border); }
.chat .who { font:600 10px system-ui, sans-serif; text-transform:uppercase;
             letter-spacing:.4px; color:var(--muted); margin-bottom:4px; }
.narr h2 { border:none; margin:26px 0 8px; }
details { margin:14px 0; }
summary { font:600 14px system-ui, sans-serif; cursor:pointer; color:var(--ink2); }
.katex { font-size:1.05em; }
@media print { .chat-details { display:none; } }
"""

RENDER_JS = """
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-tex]").forEach(el => {
    try {
      renderMathInElement(el, {throwOnError: false, errorColor: "#e34948",
        delimiters: [
          {left: "$$", right: "$$", display: true},
          {left: "\\\\[", right: "\\\\]", display: true},
          {left: "$", right: "$", display: false},
          {left: "\\\\(", right: "\\\\)", display: false}]});
    } catch (e) {}
  });
});
"""


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _md(text: str) -> str:
    """Minimal markdown for the agent narrative: ## headings, **bold**,
    *italic*, `code`, ``` fences, paragraphs. Math is left intact for KaTeX
    in the browser (which skips pre/code by default)."""
    out, para = [], []
    in_fence = False
    fence: list[str] = []

    def flush():
        if para:
            out.append("<p>" + " ".join(para) + "</p>")
            para.clear()

    for line in _esc(text).splitlines():
        s = line.strip()
        if s.startswith("```"):
            rest = s[3:].strip()
            if in_fence:                          # closing line
                out.append("<pre><code>" + "\n".join(fence) + "</code></pre>")
                fence.clear()
                in_fence = False
            elif rest.endswith("```") and len(rest) > 3:
                flush()                           # one-line ``` code ``` block
                out.append("<pre><code>" + rest[:-3].strip() + "</code></pre>")
            else:
                flush()
                in_fence = True
                if rest and " " in rest:          # content (not a language tag)
                    fence.append(rest)
        elif in_fence:
            fence.append(line)
        elif not s:
            flush()
        elif s.startswith("### "):
            flush(); out.append(f"<h3>{s[4:]}</h3>")
        elif s.startswith("## "):
            flush(); out.append(f"<h2>{s[3:]}</h2>")
        elif s.startswith("- "):
            flush(); out.append(f"<p style='margin:4px 0 4px 18px'>• {s[2:]}</p>")
        else:
            para.append(s)
    if in_fence and fence:                       # unterminated fence
        out.append("<pre><code>" + "\n".join(fence) + "</code></pre>")
    flush()
    h = "\n".join(out)
    h = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h)
    h = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", h)
    h = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", h)
    return h


def _badge(status: str) -> str:
    c = GRADE_COLOR.get(status, "#898781")
    return (f'<span class="badge" style="color:{c};border-color:{c}">'
            f'{_esc(status.replace("_", " "))}</span>')


def build_report_html(sess: dict) -> str:
    t = sess["theorem"]
    rep = sess.get("report") or {}
    asm = sess.get("lean_assembly") or {}

    # ---- proof steps + their evidence
    ev_by_step: dict[str, list] = {}
    for e in sess["evidence"]:
        ev_by_step.setdefault(e.get("step_id") or "_general", []).append(e)

    steps_html = []
    for st in sess["steps"]:
        ev = "".join(
            f'<div class="ev"><b>{_esc(e["kind"])}</b> · {_badge(e["grade"])} · '
            f'<span data-tex>{_esc(e["summary"])}</span>'
            + (f' <code>{_esc((e.get("script_path") or "").split("/")[-1])}</code>'
               if e.get("script_path") else "") + "</div>"
            for e in ev_by_step.get(st["id"], []))
        lean_note = ""
        if st.get("lean") and st["lean"].get("check") == "ok":
            lean_note = ('<span class="badge" style="color:#1baf7a;'
                         'border-color:#1baf7a;font-family:ui-monospace,monospace;'
                         'text-transform:none">λ lemma checked</span>')
        steps_html.append(f"""
        <div class="step">
          <div class="top"><b>Step {st["index"]}</b> {_badge(st["status"])}
            {lean_note}<span>{_esc(st["author"])}</span></div>
          <div data-tex>{_esc(st["statement_tex"])}</div>
          {f'<div class="just" data-tex>Justification: {_esc(st["justification"])}</div>' if st["justification"] else ""}
          {f'<div class="why" data-tex>✦ {_esc(st["discovery_rationale"])}</div>' if st.get("discovery_rationale") else ""}
          {f'<div class="comment" data-tex>{_esc(st["agent_comment"])}</div>' if st.get("agent_comment") else ""}
          {ev}
        </div>""")

    cx_html = "".join(f"""
        <div class="step" style="border-color:#4a3aa7">
          <div class="top"><b>Counterexample {_esc(c["id"])}</b>
            <span>{_esc(c["diagnostic"].replace("_", " "))}</span>
            <span>repair: {_esc(c["suggested_repair"].replace("_", " "))}</span></div>
          <div data-tex>{_esc(c["description_tex"])}</div>
          {f'<div class="comment" data-tex>{_esc(c["repair_note"])}</div>' if c.get("repair_note") else ""}
        </div>""" for c in sess["counterexamples"])

    # ---- context
    disc_html = "".join(f"""
        <div class="dItem"><div class="t" data-tex>{_esc(d["title"])}
          <span class="chip">{_esc(SOURCE_LABEL.get(d["source"], d["source"]))}</span></div>
          {f'<div class="x" data-tex>{_esc(d["tex"])}</div>' if d.get("tex") else ""}
          <div class="x" data-tex>{_esc(d["explanation"])}</div></div>"""
        for d in sess["discoveries"]) or "<p class='meta'>none recorded</p>"
    defs_html = "".join(
        f'<div class="dItem"><div class="t" data-tex>{_esc(d["term"])}</div>'
        f'<div class="x" data-tex>{_esc(d["definition"])}</div></div>'
        for d in sess["definitions"]) or "<p class='meta'>none recorded</p>"

    # ---- lean
    lean_parts = []
    if asm.get("code"):
        lean_parts.append("<h3>Assembled proof (machine-checked)</h3>"
                          f"<pre><code>{_esc(asm['code'])}</code></pre>")
    for st in sess["steps"]:
        lc = st.get("lean")
        if lc and lc.get("code") and lc["code"] not in (asm.get("code") or ""):
            lean_parts.append(f"<h3>Lemma {_esc(st['id'])} "
                              f"({_esc(lc.get('check', '?'))})</h3>"
                              f"<pre><code>{_esc(lc['code'])}</code></pre>")
    lean_html = "".join(lean_parts) or "<p class='meta'>no Lean code</p>"

    # ---- chat
    chat_html = "".join(f"""
        <div class="m {'u' if m['role'] == 'user' else 'a'}">
          <div class="who">{'you' + (' · ' + _esc(m['action'].replace('_', ' '))
                            if m.get('action') and m.get('action') != 'chat' else '')
                            if m['role'] == 'user' else 'agent'}</div>
          <div data-tex>{_esc(m["text"])}</div>
        </div>""" for m in sess["chat"])

    katex_css = KATEX_CSS.read_text() if KATEX_CSS.is_file() else ""
    katex_js = KATEX_JS.read_text() if KATEX_JS.is_file() else ""
    checked = (asm.get("check") == "ok"
               and asm.get("faithful") not in (None, "unreviewed"))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Proof report — {_esc(t["title"])}</title>
<style>{katex_css}</style>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <h1 data-tex>{_esc(t["title"])}</h1>
  <div class="meta">proof report · {_esc(sess["status"].replace("_", " "))} ·
    {'λ machine-checked (Lean 4 / Mathlib)' if checked else 'not machine-checked'} ·
    generated {_esc(rep.get("generated_at", ""))} · session {_esc(sess["id"])}</div>
  <div class="stmt" data-tex>{_esc(t.get("tex") or t.get("text") or "")}</div>

  <div class="narr" data-tex>{_md(rep.get("narrative", "_no narrative recorded_"))}</div>

  <h2>The proof</h2>
  {"".join(steps_html) or "<p class='meta'>no steps</p>"}
  {cx_html}

  <h2>Context</h2>
  <h3>Relevant results</h3>{disc_html}
  <h3>Objects &amp; definitions</h3>{defs_html}

  <h2 class="lean">Lean formalization</h2>
  <div class="lean">{lean_html}</div>

  <h2>Conversation transcript</h2>
  <details class="chat-details"><summary>show the full conversation
    ({len(sess["chat"])} messages)</summary>
    <div class="chat">{chat_html}</div>
  </details>
</div>
<script>{katex_js}</script>
<script>{RENDER_JS}</script>
</body>
</html>"""


def write_report(sess: dict) -> str:
    """Build and persist the report; returns the session-relative path."""
    out = workspace_dir(sess["id"]).parent / "report.html"
    out.write_text(build_report_html(sess), encoding="utf-8")
    return "report.html"
