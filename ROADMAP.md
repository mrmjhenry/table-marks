# Roadmap

v1 (shipped) is the pipeline and map documented in [README.md](README.md). This
roadmap collects the planned improvements, in suggested execution order. Nothing
below is implemented yet.

### Phasing

| phase | items | rationale |
|---|---|---|
| **P1 — map quality** ✅ shipped | 1 LaTeX · B8 shareable URLs · B7 path finding | pure frontend, $0, immediate payoff |
| **P2 — aboutness** | 3a MSC · 3b clusters · B6 ontology browser · B9 bridge-objects report | cheap batches + reuses embedding infra |
| **P3 — coverage** | B1 withheld recovery · B2 semantic dedup · B3 external problem lists | grow the corpus *before* the expensive knowledge passes so they run once |
| **P4 — knowledge** | 2 proof status (web search) · B4 logical relations · B5 Lean/mathlib status | costliest; benefits from full corpus |
| **P5 — automation** | B10 living map (auto-refresh) | automate only once the pipeline shape is stable |

---

## 1. Render LaTeX in the detail view (KaTeX, vendored)

The map is self-contained (zero external requests), so KaTeX must be vendored,
not CDN-loaded.

- **Assets:** download `katex.min.js`, `katex.min.css`, `auto-render.min.js`,
  and the woff2 fonts once into `vendor/katex/`; inline fonts into the CSS as
  `data:` URIs. Adds ~1.2–1.5 MB to the final HTML.
- **Data:** add a `render_tex` field in `scripts/01_fetch.py` = lightly-cleaned
  `body_tex` (keeps `$…$` intact — the existing `display_text` prefers
  `plain_text`, which mangles math). **Do not change `content_hash` or
  `display_text`** — the hash keys `extractions.jsonl` and must stay stable so
  no re-extraction is triggered. Carry `render_tex` through `04_graph.py` into
  node payloads (cap 4,000 chars).
- **Template:** `templates/viz.html` gets `__KATEX_CSS__` / `__KATEX_JS__`
  placeholders; `scripts/05_render.py` injects the vendored assets. The panel
  renders `render_tex` via `renderMathInElement(el, {throwOnError: false, …})`,
  falling back to `display_text` if KaTeX throws or the field is empty.
- **Verification:** screenshot the panel on a math-heavy conjecture; confirm no
  new external URLs; confirm graceful fallback on broken TeX.
- **Cost:** $0.

## 2. Connect conjectures to established proofs (web search)

Determine, per conjecture, whether it has since been proved/disproved, and link
the resolving work.

- **New stage `scripts/06_status.py`** (same resumable pattern as 02: keyed by
  `content_hash` → `data/status.jsonl`, Batches API, structured output). Model
  `claude-sonnet-5` + the `web_search_20260209` server tool (`max_uses: 3`).
- **Prompt:** give title, statement, source arXiv id + publication date, and the
  dataset's existing label + rationale as context. Ask: search for later work
  resolving this conjecture. Require URL evidence for any non-open verdict; when
  evidence is unclear, answer `unknown` — never infer resolution. Schema:
  `{status: proved|disproved|partially_resolved|open|unknown, resolved_by:
  {title, year, url}|null, evidence_note, confidence}`.
- **Scope control:** web search is ~$10/1k searches plus tokens. Phase it: first
  the ~800 rows with `latest_label = real_open_conjecture` AND
  `interestingness ≥ 0.5` (est. $15–25), then `--all` for the rest. Free prior:
  rows already labeled `not_real_conjecture` with a resolution rationale get
  status seeded from that rationale without search.
- **Map changes:** status as a node stroke/glyph (category color preserved),
  a status filter row, and a "Resolution" panel section linking the resolving
  paper.
- **Verification:** hand-check 15 famous conjectures with known status
  (e.g. Aharoni–Korman → disproved 2024); every non-open verdict carries a URL.

## 3a. MSC 2020 subject codes (LLM)

Standard fine-grained classification (e.g. `05C15` graph coloring, `11G05`
elliptic curves over global fields).

- Vendor the MSC 2020 taxonomy (machine-readable code→name list) into
  `vendor/msc2020.json` at 2-, 3-, and 5-char levels.
- **New stage `scripts/07_msc.py`**: batch job assigning 1–2 five-char MSC codes
  per conjecture from title + statement + the paper's abstract (join the
  dataset's `papers` config on `arxiv_id` for `summary`). Validate returned
  codes against the vendored list; on invalid, fall back to the 2-digit class.
  Est. ~$2–3.
- **Map changes:** MSC chips in the panel (click = filter); MSC filter dropdown;
  optional "color by MSC top-level" toggle — this also fixes the 377
  "uncategorized" nodes that currently have no arXiv category.
- **Verification:** code-validity ≥ 98%; spot-check 20 assignments;
  distribution sanity (05-xx and 11-xx should dominate).

## 3b. Embedding clusters (data-driven topics)

A second, taxonomy-free lens that can cut across MSC lines.

- **New stage `scripts/08_clusters.py`**: embed title + statement with a local
  sentence-transformer (`all-MiniLM-L6-v2`), cluster with HDBSCAN
  (scikit-learn's implementation), then one Claude call per cluster (~40–80
  expected) to name it from its top-10 central members →
  `data/clusters.jsonl`. Est. <$1 API + a one-time ~90 MB model download.
- **Map changes:** cluster name in panel; cluster filter dropdown; optional
  "color by cluster" toggle (top ~7 clusters + other).
- **Verification:** silhouette/noise fraction printed; eyeball 10 cluster
  names against members; cross-tab clusters vs MSC.

---

## Backlog

### B1. Recover the withheld 53%
The dataset withholds text for 2,181 rows but records `source_url` (arXiv
e-print tarball), `source_file`, and `start_line`–`end_line`. New stage
`scripts/00_recover.py`: download each e-print (rate-limited, cached to
`data/eprints/`), read the recorded line span, run the same LaTeX cleaning as
01, and merge into `conjectures.parquet` with a `text_source: dataset|recovered`
flag. Recovered text is for **local research use only — must not be
republished** (that's why it's withheld); `data/` stays gitignored. Downstream
stages pick the new rows up automatically via content-hash caching (+~$2.50
extraction). Doubles the map to ~4,100 conjectures.

### B2. Semantic dedup
v1 dedup is exact-text. Reuse 3b's embeddings: flag pairs with cosine
similarity ≥ ~0.95 AND near-identical object sets as restatement candidates;
LLM-confirm (expect only dozens); collapse confirmed pairs the way 01 collapses
exact matches.

### B3. External problem lists
Source adapters for the Erdős problems database, Open Problem Garden, and
Wikipedia unsolved-problems lists → same record shape → same extract/normalize
stages → differently-shaped nodes with a source filter. Cross-link to arXiv
conjectures via B2's semantic matching. Est. ~$2–4.

### B4. Logical relations (typed edges)
Directed edges: *generalizes / implies / special-case-of / equivalent-to*.
Candidates only — existing high-weight object edges plus B2's near-duplicate
pairs (~top 5k pairs). Batch job asks for the relation or `none` with
justification. Render as arrows distinct from similarity edges. Est. ~$5–10.

### B5. Lean/mathlib formalization status
Check whether each conjecture (or its resolution) is stated/formalized in
Lean's mathlib: LeanSearch/Moogle-style APIs where available, else local
text+LLM matching against a mathlib clone. Node badge + "formalized" filter.
Est. ~$2–5. Sanity anchor: the Aharoni–Korman counterexample is Lean-verified
and must be found.

### B6. Object ontology browser
`vocab.json` already carries `parent` relations and areas. Collapsible tree
sidebar (area → parent object → object) driving the same filter as clicking an
object chip, with per-object conjecture counts. Frontend-only, $0.

### B7. Path finding
Select a node, shift-click another: highlight the shortest-strongest connecting
path (BFS with inverted weights) and list the shared objects at each hop.
Frontend-only, $0.

### B8. Shareable URLs
Encode selected node id + active filters in `location.hash`; restore on load.
Frontend-only, $0.

### B9. Bridge-objects report
For each object, compute the category/MSC entropy of the conjectures it
touches; rank high-df, high-entropy objects — the field bridges. Output
`reports/bridge_objects.md` plus an in-map "bridges" highlight mode. $0.

### B10. Living map (auto-refresh)
The dataset keeps ingesting new arXiv papers. A scheduled job re-runs 01→05
incrementally — content-hash caching means only new rows hit the API (pennies
per delta) — then re-renders the HTML. Scheduled last, once the pipeline shape
is stable.

---

## Shared plumbing

- `scripts/04_graph.py`: merge `status.jsonl` / `msc.jsonl` / `clusters.jsonl`
  into node payloads when present (each optional).
- `templates/viz.html`: panel sections + filter rows for status/MSC/cluster;
  color-mode toggle (category | MSC | cluster); KaTeX rendering.
- `README.md`: new methods sections per improvement, with real numbers.
- `requirements.txt`: + `sentence-transformers`, `scikit-learn`.

## Cost estimates

| item | est. cost |
|---|---|
| 1 LaTeX (KaTeX vendored) | $0 |
| 3a MSC codes | $2–3 |
| 3b embedding clusters | <$1 |
| 2 proof status (high-interest ~800 first) | $15–25 (full corpus ~$35–50) |
| B1 withheld recovery | ~$2.50 |
| B2 semantic dedup | <$1 |
| B3 external problem lists | ~$2–4 |
| B4 logical relations | ~$5–10 |
| B5 Lean/mathlib status | ~$2–5 |
| B6–B9 | $0 |
| B10 living map | pennies per refresh |
| **everything** | **~$35–55** (with full-corpus proof status: ~$55–80) |
