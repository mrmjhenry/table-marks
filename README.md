# Table Marks

An interactive theorem-proving workspace: state a theorem or conjecture in
LaTeX, then prove it step by step in a chat with an agent that **checks your
work** — grading every claim, verifying with executable scripts, hunting for
counterexamples, and (optionally) machine-checking the result in Lean 4. Hand
it a hint request, a single subgoal, or the whole remaining proof; the division
of labor is yours.

It ships with the **OpenConjecture Map** — an interactive map of ~4,000 open
conjectures auto-extracted from arXiv, linked by the mathematical objects they
concern — which doubles as a conjecture picker: every node has a *prove this*
button that opens it in the workspace.

**Demo video:** [demo.mp4](demo.mp4) (≈2 min: the √2 walkthrough, the UI, and
the map).

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=…            # or an active `claude` CLI login
uvicorn app.server:app --port 8765
open http://127.0.0.1:8765/
```

- `/` — the workspace (also at `/workspace` for older links).
- `/?demo=sqrt2` — a guided walkthrough of the √2-irrationality proof that
  teaches the interface, including watching the agent catch a deliberately
  unjustified step.
- `/openconjectures` — the conjecture map, with *prove this* buttons live.
  (The map is also a standalone artifact: open `conjecture_map.html` directly
  in a browser, no server needed.)

Environment knobs: `PROOF_AGENT_MODEL=claude-sonnet-5` (or any model id)
overrides the agent model; `PROOF_STUB_AGENT=1` runs a no-API stub for UI
development.

## The workspace

**Chat-first proving.** The home page is a LaTeX statement box with a live
KaTeX preview. On submit the statement renders (editable any time — context is
re-discovered on edit) and the conversation below accepts proof steps,
questions, or narrative. The agent records each step you state, splits
compound messages, and checks every step before grading it.

**Discovery.** Submitting a theorem triggers a discovery pass that populates a
hideable drawer:

- *Relevant results* — theorems, lemmas, and conjectures gathered from
  [TheoremSearch](https://github.com/uw-math-ai/TheoremSearch) (semantic
  search over ~9M theorems, wired in as a remote MCP server), from the
  conjecture map's graph neighborhood, and from the model's own knowledge.
  Every item is source-labeled; recalled results are explicitly
  `[UNVERIFIED-CITATION]` until checked.
- *Objects & definitions* — every mathematical object in the statement,
  extracted with a definition and a note on why it matters here.

The drawer's second tab is the **condensed proof**: graded step rows, the
evidence log (every check the agent ran, linked to its saved script),
counterexample cards, and Lean generation.

**Grading discipline.** The agent runs on the Claude Agent SDK with a
`prove-conjecture` skill distilled from published research on how
mathematicians actually work (Lakatos's *Proofs and Refutations*, Pólya's
heuristics, Thurston, Gowers's human-oriented theorem proving, the CERME10
case study) extended with documented lessons from 2024–26 LLM-assisted
proving. Concretely:

- Every claim is graded **verified / partially verified / unverified /
  refuted**, with an oracle-tier label (self-check < executable falsification
  < independent audit < machine-checked). A true-but-unjustified step earns
  only *partially verified* — the demo makes a point of this.
- Verification means **executable scripts** (SymPy, enumeration), sandboxed
  (command allowlist + macOS Seatbelt write-confinement) and saved with the
  session as regression checks — never prose judgment alone.
- Counterexamples get the Lakatos treatment: a global/local diagnostic and a
  suggested repair (lemma-incorporation, exception-barring, …) rendered as a
  card in the proof tab.
- Assistance is a spectrum, per action: *hint* (one nudge, no spoilers),
  *suggest next* (one proposed step, left for you), *check*, *delegate
  subgoal*, *prove remaining* (the full loop), *challenge* (counterexample
  hunt).

Sessions persist under `sessions/` (state JSON + every script and Lean file
the proof produced) and survive server restarts — the agent conversation
resumes, or falls back to a state recap rebuilt from disk.

**Optional Lean machine-checking.** With a Lean toolchain installed, the
workspace can formalize the proof against a pinned Mathlib: a `lean-formalizer`
subagent iterates code against the compiler (`app/lean.py` — deterministic,
no LLM in the checking path), and the main agent must affirm the formal
statement's *faithfulness* to the informal one before anything earns the
`λ machine-checked` badge — a compiling proof of the wrong statement is worth
nothing. One-time setup:

```bash
brew install elan-init            # Lean version manager (or the official installer)
cd lean && lake exe cache get     # pinned toolchain + prebuilt Mathlib (~5 GB)
```

Without the toolchain everything else works; the Lean UI stays hidden
(`GET /api/lean/status` reports availability).

## Repository layout

```
app/                                 the workspace: FastAPI server, agent runner
                                     (Claude Agent SDK), Lean checker, single-file
                                     vanilla-JS frontend, sqrt2 guided demo
.claude/skills/prove-conjecture/     the proving skill: workflow, verification
                                     protocol, failure catalog, script templates
.claude/agents/lean-formalizer.md    the Lean formalization subagent
lean/                                pinned Lean 4 + Mathlib project (optional)
conjecture_map.html                  the map (self-contained; open in a browser)
templates/viz.html                   map template (canvas force layout)
scripts/00…11_*.py                   the map's data pipeline (see § Reproducing)
openconjecture_data_dictionary.pdf   data dictionary for the source dataset
ROADMAP.md                           shipped scorecard + what remains
demo.mp4                             the demo video
data/                                gitignored — pipeline intermediates. Kept
                                     local partly for licensing reasons: derived
                                     arXiv text isn't republished beyond what the
                                     source dataset permits.
sessions/                            gitignored — proof-workspace sessions
```

## The OpenConjecture Map

An interactive map of mathematical conjectures, connected by the
**mathematical objects they concern** rather than only by arXiv subject
category. Built on the
[davisrbr/openconjecture](https://huggingface.co/datasets/davisrbr/openconjecture)
dataset. `conjecture_map.html` is a single self-contained file — no server, no
network access, zero external requests.

The dataset contains ~4,100 conjectures auto-extracted from arXiv LaTeX
sources, labeled by an LLM as real open conjectures or not, and scored for
interestingness and viability. Its only "aboutness" signal is the paper's
arXiv category — a coarse, single-axis label. The map answers: **which
conjectures work with the same mathematical objects?** The dataset has no
entity annotations, so the pipeline extracts them:

```
dataset → extract objects (LLM) → normalize to a canonical vocabulary
        → project a weighted conjecture–conjecture graph → interactive map
```

Everything below documents that pipeline and its actual run results.

### Data

Source: config `conjectures` of `davisrbr/openconjecture` (single `train`
split, 4,147 rows). Relevant fields: `title`, `plain_text` / `body_tex` (the
statement), `primary_category`, `latest_label` (`real_open_conjecture` /
`not_real_conjecture` / `uncertain`, assigned by gpt-5-mini),
`latest_interestingness_score`, `latest_viability_score`, `text_withheld`,
`abs_url`.

**Withheld-text recovery** (`scripts/00_recover.py`, optional stage): 2,181
rows (53%) have `text_withheld = true` — their text is not republishable
because the source paper is under arXiv's non-exclusive-distribution license.
The dataset records exact provenance (`source_url`, `source_file`,
`start_line`–`end_line`), so this stage downloads each e-print (rate-limited
to 1 request per 3 s, cached to `data/eprints/`), reads the recorded line
span, and merges the text back in with a `text_source: recovered` flag.
**Recovered text is used for local analysis only and is never republished**:
`04_graph.py` redacts it from the publishable `conjecture_map.html`
(metadata, extracted entities, and arXiv links remain; the statement itself
says to follow the link), while a gitignored `conjecture_map_local.html`
carries the full text for personal use. Recovery succeeded for **2,061 of
2,181 rows (94.5%)**; the 120 failures are mostly PDF-only submissions with
no LaTeX source.

**Filtering decisions** (`scripts/01_fetch.py`):
- **All labels kept.** Objects are extracted for every with-text row and
  `latest_label` is carried as a node attribute, so the map can filter to
  open conjectures without discarding the rest.
- **Text construction.** Prefer `plain_text`; fall back to lightly-cleaned
  `body_tex` (strip comments, `\label{}`, citations → `[ref]`,
  `\begin/\end` wrappers; keep `$…$` math verbatim). Two variants are stored:
  `model_text` (≤ 6,000 chars, fed to the LLM) and `display_text`
  (≤ 4,000 chars, shown in the map).
- **Dedup by content hash.** Famous conjectures are restated across papers.
  Statements are hashed (whitespace-normalized, lowercased) keeping the
  earliest-published row per hash and recording all `arxiv_id`s.

Pipeline row counts from the actual run (after withheld-text recovery):

| stage | rows |
|---|---|
| dataset total | 4,147 |
| with text (1,966 public + 2,061 recovered) | 4,027 |
| non-empty after cleaning | 4,016 |
| after dedup | **3,952** |
| labeled `real_open_conjecture` | 3,191 |

### Object extraction (LLM)

`scripts/02_extract.py` — model `claude-sonnet-5` via the Anthropic **Message
Batches API** (50% price reduction; results keyed by content hash, so the run
is resumable and idempotent). The shared system prompt carries a
`cache_control` breakpoint so it is prompt-cached across all requests;
structured output is enforced with a JSON schema. The prompt asks a
"research mathematician indexing conjectures for a knowledge graph" to list
2–8 standard-named objects per conjecture, most central first, marked
primary/secondary, excluding generic words (number, function, set, …) unless
part of a standard compound object. A `--sync --limit N` flag runs direct API
calls for prompt iteration; the full batch was submitted only after a
hand-reviewed dry run.

**Results (actual run):** all conjectures extracted; median **4 objects per
conjecture**; only 0.2% of rows returned no objects; 123 rows were flagged
`looks_like_conjecture: false` by the extractor (mostly definitions or
theorems sitting in a `\begin{conjecture}` environment).

### Normalization — the canonical vocabulary

Raw extractions are noisy ("finite poset" vs "poset"). `scripts/03_normalize.py`
canonicalizes in two passes: **Pass A**, mechanical folding (NFC-normalize,
lowercase, strip TeX remnants, singularize the head noun with a
guarded rule set); **Pass B**, LLM-assisted merge — anchor terms (df ≥ 3) are
synonym-merged in one call, tail terms are mapped onto anchors / kept as new
canonicals / discarded, with `map_to` targets validated in code, and each
canonical assigned a parent area from a fixed 20-item list. Review artifacts
(`data/review_normalize.txt`) flag mega-merges and edit-distance-≤2 pairs.

**Results:** 4,252 folded terms → **1,977 canonical objects** (982 appearing
in ≥ 2 conjectures). Every flagged near-pair (graph/digraph, matrix/matroid,
cohomology/homology) was a genuinely distinct pair correctly *not* merged.

### A typed vocabulary

The vocabulary is deliberately narrower than "mathematical object"
philosophically construed (paradigm cases like *number* are excluded as
non-discriminative) and broader in admitting unsaturated concepts — but typed,
following Frege's saturated/unsaturated distinction:

| type | definition | examples |
|---|---|---|
| `structure` | saturated kind — you can exhibit an instance | poset, elliptic curve, matroid |
| `invariant` | quantity/function *of* a structure | chromatic number, genus |
| `property` | predicate or relation *of* structures | log concavity, density |
| `statement` | named theorem/conjecture referred to as a thing | Riemann hypothesis |
| `discarded` | proof techniques & meta-mathematical words | polynomial method, upper bound |

`scripts/03b_type.py` types every entry (schema-enforced, checkpointed).
**Results:** 3,795 entries — 2,664 structures, 667 invariants, 194 properties,
195 statements, 75 discarded; 417 individuals ("Monster group"). With type
weighting, edge weight decomposes as **structure 81%, invariant 16%, property
2%, statement 2%** — properties no longer masquerade as mathematical kinship.

### Graph construction

`scripts/04_graph.py` projects the conjecture↔object incidence to a weighted
conjecture–conjecture graph:

- **IDF² weighting:** edge weight = Σ idf(o)² over shared objects — one shared
  *rare* object counts far more than several common ones.
- **Type weighting:** structure ×1.0, statement ×1.5, invariant ×0.8,
  property ×0.4, discarded ×0.
- **Ubiquity cutoff** (objects in > 15% of conjectures excluded from the
  projection) and **pruning** (union of each node's top-6 edges, then drop the
  bottom weight quartile).

Each edge records *which* objects it shares — relatedness is always
explainable in the UI, never a bare similarity score. **Results:** 3,952
nodes, 12,119 edges after pruning, giant component 88%, max degree 25.

### Further annotations

- **MSC 2020 codes** (`scripts/07_msc.py`): 1–2 five-char codes per
  conjecture, validated against the vendored official taxonomy
  (`vendor/msc2020.json`, from [msc2020.org](https://msc2020.org),
  CC BY-NC-SA). All 3,952 coded, 100% valid. Drives an MSC color mode.
- **Embedding clusters** (`scripts/08_clusters.py`): local `all-MiniLM-L6-v2`
  embeddings + HDBSCAN → **208 named clusters** covering 44% (the rest is
  honestly unclustered); near-duplicate pairs (cosine ≥ 0.93) feed the
  relations stage.
- **Logical relations** (`scripts/09_relations.py`): 6,076 candidate pairs
  classified strictly → **701 typed relations** (387 generalizes, 183
  same-conjecture, 102 implies, 29 equivalent; 88% none, which is the intended
  strictness). Rendered as violet directional arrows with justifications.
- **Lean/mathlib** (`scripts/10_lean.py`): every statement checked against
  [LeanSearch](https://leansearch.net) with LLM verification. **An honest
  near-null: 3 related hits, zero statement-formalized** — research-frontier
  conjectures are essentially absent from mathlib.
- **Bridge entities** (`scripts/11_bridges.py`): MSC-entropy ranking of
  structures → `reports/bridge_objects.md`. Top bridges: probability
  distribution, polynomial, matrix, sphere, field.

### Visualization

`templates/viz.html` + `scripts/05_render.py` → `conjecture_map.html`:
hand-rolled canvas force layout, vendored KaTeX (fonts inlined as data URIs —
zero external requests), pan/zoom, search, per-node detail panel with rendered
statements and clickable typed entity chips, three color modes (arXiv / MSC /
cluster), an ontology browser, Dijkstra path-finding between any two nodes
(shift-click), typed relation arrows, Lean badges, and shareable URLs (full
view state in `location.hash`). When the workspace server is running, each
node panel gains the *prove this* button.

### Limitations & threats to validity

- **LLM extraction noise:** object lists are model judgments; expect
  occasional missed objects or over-specific names. `centrality` is heuristic.
- **Normalization merge errors:** Pass B can under- or over-merge; review
  files flag likely cases but not all.
- **Selection bias from licensing:** only CC-licensed papers contribute
  public text; if licensing practice correlates with field, the map's balance
  is skewed.
- **Upstream label noise:** open/interestingness/viability labels come from a
  single model in the source dataset, inherited unaudited.
- **Restatement dedup is exact-text only:** the same conjecture phrased two
  ways appears as two heavily-linked nodes.

## Reproducing the map

```bash
python scripts/00_recover.py                   # optional: recover withheld text (~1 h, arXiv rate-limited)
python scripts/01_fetch.py                     # ~1 min, downloads the dataset
python scripts/02_extract.py --sync --limit 20 # review extraction quality first
python scripts/02_extract.py                   # full batch; resumable, polls until done
python scripts/03_normalize.py                 # incremental LLM canonicalization
python scripts/03b_type.py                     # type the vocabulary
python scripts/07_msc.py                       # MSC 2020 codes (batch)
python scripts/08_clusters.py                  # local embeddings + clusters + near-dup pairs
python scripts/04_graph.py                     # build graph (needed before 09)
python scripts/09_relations.py                 # logical relations (batch)
python scripts/10_lean.py                      # LeanSearch + verification (rate-limited)
python scripts/04_graph.py                     # rebuild with all annotations merged
python scripts/11_bridges.py                   # bridge-entities report
python scripts/05_render.py                    # → conjecture_map.html (+ _local variant)
```

Every stage caches to `data/` and skips completed work, so interrupting and
rerunning never re-pays for finished calls. **Actual cost:** the whole map
(v1 + full-corpus expansion with recovery, MSC, clusters, relations, Lean
checks) ≈ **$23** in API usage and ~5 hours of wall-clock, dominated by rate
limits and batch queue time.

## License

Code is MIT-licensed (see `LICENSE`). Third-party material: the vendored
KaTeX build is MIT (`vendor/katex/LICENSE`); the MSC 2020 taxonomy
(`vendor/msc2020.json`) is CC BY-NC-SA from msc2020.org; conjecture text shown
in the map comes from CC-licensed arXiv papers, attributed via author lists
and arXiv links on every node, with non-republishable recovered text redacted
from the published map.
