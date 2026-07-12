# Roadmap

v1 (the pipeline and map documented in [README.md](README.md)) shipped first;
most of the original improvement roadmap has since shipped too. This file
tracks what's done (with actuals) and specs what remains.

## Status

| phase | items | status |
|---|---|---|
| **P1 — map quality** | 1 LaTeX · B8 shareable URLs · B7 path finding | ✅ shipped |
| **P2 — aboutness** | 3a MSC · 3b clusters · B6 ontology browser · B9 bridge report | ✅ shipped |
| **P3 — coverage** | B1 withheld recovery ✅ · B2 semantic dedup · B3 external lists | ◐ B1 shipped |
| **P4 — knowledge** | 2 proof status · B4 logical relations ✅ · B5 Lean status ✅ | ◐ B4+B5 shipped |
| **P5 — automation** | B10 living map | not started |
| *(unplanned)* | typed entity vocabulary (structure/invariant/property/statement) | ✅ shipped |

## Shipped — results

Methodology for everything below lives in the README; this is the scorecard.

- **1. LaTeX rendering** — KaTeX vendored (fonts as data URIs, zero external
  requests); statements render from `render_tex` with plain-text fallback. $0.
- **B8. Shareable URLs** — selected node + all filters + color mode encode into
  `location.hash`, restored on load. $0.
- **B7. Path finding** — shift-click two nodes → Dijkstra on inverted weights,
  per-hop shared entities in the panel. $0.
- **Typed vocabulary** — all entities typed (2,664 structures / 667 invariants /
  194 properties / 195 statements / 75 discarded; 417 individuals); type-scaled
  edge weights (structure 81% of total edge weight, property just 2%). ~$1.
- **3a. MSC codes** — all 3,952 conjectures coded, 100% valid against the
  vendored MSC 2020 taxonomy; MSC color mode in the map. ~$3.
- **3b. Embedding clusters** — 208 named clusters covering 44%; near-dup pairs
  as a byproduct. <$1.
- **B6. Ontology browser** — collapsible area → structure tree driving the
  entity filter. $0.
- **B9. Bridge report** — `reports/bridge_objects.md`: MSC-entropy ranking;
  top bridges: probability distribution, polynomial, matrix, sphere, field. $0.
- **B1. Withheld recovery** — 2,061/2,181 rows (94.5%) recovered from arXiv
  e-print line spans; corpus 1,936 → 3,952. Published map redacts recovered
  text (gitignored `conjecture_map_local.html` keeps it). ~$3 extraction delta.
- **B4. Logical relations** — 6,076 pairs classified strictly → 701 typed
  relations (387 generalizes / 183 restates / 102 implies / 29 equivalent);
  violet arrows + justifications in the panel. ~$8.
- **B5. Lean/mathlib** — all statements checked via LeanSearch + LLM
  verification. Honest near-null: 3 related hits, zero formalized statements
  (mathlib doesn't contain research-frontier conjectures; standalone Lean repos
  aren't indexed). ~$1.

Phase-2 total ≈ $20 ($15.90 in half-price batches). Project total ≈ $23.

---

## Remaining

### 2. Connect conjectures to established proofs (web search)

The largest outstanding item. Determine, per conjecture, whether it has since
been proved/disproved, and link the resolving work.

- **New stage `scripts/06_status.py`** (same resumable pattern as 02: keyed by
  `content_hash` → `data/status.jsonl`, Batches API, structured output). Model
  `claude-sonnet-5` + the `web_search_20260209` server tool (`max_uses: 3`).
- **Prompt:** title, statement, source arXiv id + publication date, and the
  dataset's label + rationale as context. Require URL evidence for any non-open
  verdict; when evidence is unclear, answer `unknown` — never infer resolution.
  Schema: `{status: proved|disproved|partially_resolved|open|unknown,
  resolved_by: {title, year, url}|null, evidence_note, confidence}`.
- **Scope control:** web search ≈ $10/1k searches + tokens. Phase it: first the
  ~1,600 open-labeled rows with `interestingness ≥ 0.5` (est. $30–45 at the
  doubled corpus), then `--all`. Rows already labeled `not_real_conjecture`
  with a resolution rationale get status seeded free.
- **Map:** status glyph/stroke per node, status filter, "Resolution" panel
  section. Feeds a future timeline/survival analysis.
- **Verification:** hand-check 15 famous conjectures with known status
  (Aharoni–Korman → disproved 2024); every non-open verdict carries a URL.

### B2. Semantic dedup (apply the collapse)

The candidate pairs already exist (`data/dup_candidates.jsonl`, 379 pairs at
cosine ≥ 0.93) and the relations pass classified 183 pairs as
`same_conjecture`. Remaining work: collapse confirmed restatements the way 01
collapses exact matches (keep earliest, union `all_arxiv_ids`), re-run graph +
render. <$1 (mostly done already — could reuse the `same_conjecture` verdicts
directly).

### B3. External problem lists

Source adapters for the Erdős problems database, Open Problem Garden, and
Wikipedia unsolved-problems lists → same record shape → same extract/normalize
stages → differently-shaped nodes with a source filter; cross-link via
embedding matching. Est. ~$3–5 at current extraction prices.

### B10. Living map (auto-refresh)

A scheduled job re-runs the pipeline incrementally as the dataset ingests new
arXiv papers — every stage is now hash-keyed and incremental, so deltas cost
pennies. Schedule 00→05 (+07/08/09 deltas), re-render, optionally republish.
Best done last, once item 2 settles the pipeline's final shape.
