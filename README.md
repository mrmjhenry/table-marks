# OpenConjecture Map

An interactive map of mathematical conjectures, connected by the **mathematical
objects they concern** rather than only by arXiv subject category. Built on the
[davisrbr/openconjecture](https://huggingface.co/datasets/davisrbr/openconjecture)
dataset.

**Deliverable:** `conjecture_map.html` — a single self-contained file; open it in
any browser (no server, no network access needed).

## Repository layout

```
conjecture_map.html                  the map (self-contained; open in a browser)
scripts/01_fetch.py … 05_render.py   the 5-stage pipeline (see § Reproducing)
templates/viz.html                   visualization template (canvas force layout)
app/                                 proof workspace: FastAPI + Claude Agent SDK
                                     interactive theorem proving (see § Proof
                                     workspace)
lean/                                pinned Lean 4 + Mathlib project used by the
                                     workspace's machine-checking layer (optional)
.claude/skills|agents/               prove-conjecture skill + lean-formalizer
                                     subagent driving the workspace agent
openconjecture_data_dictionary.pdf   data dictionary for the source dataset
ROADMAP.md                           planned improvements (LaTeX rendering, proof
                                     linking, MSC/topic classification, …)
data/                                gitignored — cached pipeline intermediates
                                     (extractions, vocabulary, graph). Kept local
                                     partly for licensing reasons: derived text
                                     from arXiv papers should not be republished
                                     beyond what the source dataset permits.
sessions/                            gitignored — proof-workspace sessions (state
                                     JSON + the scripts/Lean files each proof
                                     produced)
```

Code is MIT-licensed (see `LICENSE`). Conjecture text shown in the map comes from
CC-licensed arXiv papers, attributed via author lists and arXiv links on every
node.

---

## 1. Motivation & research question

The OpenConjecture dataset contains ~4,100 conjectures auto-extracted from arXiv
LaTeX sources, each labeled by an LLM as a real open conjecture or not, and scored
for interestingness and viability. The only "aboutness" signal it ships is the
paper's arXiv category (`math.CO`, `math.NT`, …) — a coarse, single-axis label.

The question this project answers: **which conjectures work with the same
mathematical objects?** Two conjectures in different arXiv categories can both
concern, say, symmetric functions or elliptic curves; category labels can't see
that. The dataset has **no entity or object annotations**, so the objects must be
extracted from the conjecture text itself. That is what this pipeline does:

```
dataset → extract objects (LLM) → normalize to a canonical vocabulary
        → project a weighted conjecture–conjecture graph → interactive map
```

## 2. Data

Source: config `conjectures` of `davisrbr/openconjecture` (single `train` split,
4,147 rows). Relevant fields: `title`, `plain_text` / `body_tex` (the statement),
`primary_category`, `latest_label` (`real_open_conjecture` /
`not_real_conjecture` / `uncertain`, assigned by gpt-5-mini),
`latest_interestingness_score`, `latest_viability_score`, `text_withheld`,
`abs_url`.

**Withheld-text recovery** (`scripts/00_recover.py`, optional stage): 2,181 rows
(53%) have `text_withheld = true` — their text is not republishable because the
source paper is under arXiv's non-exclusive-distribution license. The dataset
records exact provenance (`source_url`, `source_file`, `start_line`–`end_line`),
so this stage downloads each e-print (rate-limited to 1 request per 3 s, cached
to `data/eprints/`), reads the recorded line span, and merges the text back in
with a `text_source: recovered` flag. **Recovered text is used for local
analysis only and is never republished**: `04_graph.py` redacts it from the
publishable `conjecture_map.html` (metadata, extracted entities, and arXiv links
remain; the statement itself says to follow the link), while a gitignored
`conjecture_map_local.html` carries the full text for personal use. Recovery
succeeded for **2,061 of 2,181 rows (94.5%)**; the 120 failures are mostly
PDF-only submissions with no LaTeX source.

**Filtering decisions** (`scripts/01_fetch.py`):
- **All labels kept.** We extract objects for every with-text row and carry
  `latest_label` as a node attribute, so the map can filter to open conjectures
  (1,596 of them) without discarding the rest.
- **Text construction.** Prefer `plain_text`; fall back to lightly-cleaned
  `body_tex` (strip comments, `\label{}`, citations → `[ref]`,
  `\begin/\end` wrappers; keep `$…$` math verbatim). Two variants are stored:
  `model_text` (≤ 6,000 chars, fed to the LLM) and `display_text` (≤ 4,000 chars,
  shown in the map).
- **Dedup by content hash.** Famous conjectures are restated across papers
  (e.g. the Aharoni–Korman conjecture). We hash the whitespace-normalized,
  lowercased statement text and keep the earliest-published row per hash,
  recording all `arxiv_id`s. This collapsed **28 restatements**, leaving
  **1,936 distinct conjectures**.

Pipeline row counts from the actual run (after withheld-text recovery):

| stage | rows |
|---|---|
| dataset total | 4,147 |
| with text (1,966 public + 2,061 recovered) | 4,027 |
| non-empty after cleaning | 4,016 |
| after dedup | **3,952** |
| labeled `real_open_conjecture` | 3,191 |

## 3. Object extraction (LLM)

`scripts/02_extract.py` — model **`claude-sonnet-5`** via the Anthropic
**Message Batches API** (50% price reduction; results keyed by `custom_id` =
content hash, so the run is resumable and idempotent). The shared system prompt
carries a `cache_control` breakpoint so it is prompt-cached across all requests.
Structured output is enforced with a JSON schema (`output_config.format`), so
responses are guaranteed-parseable JSON.

**System prompt** (verbatim, minus the three few-shot examples shown in the
script):

> You are a research mathematician indexing conjectures for a knowledge graph.
> Given a conjecture's title and statement, list the mathematical objects it
> concerns.
>
> Rules:
> 1. Use standard, generic names in lowercase singular form: "elliptic curve",
>    not "the elliptic curves E/Q in the statement".
> 2. Keep a qualifier in the name only when it denotes a genuinely different
>    object ("moduli space of curves" is its own object; "finite poset" is a
>    "poset" with qualifier "finite").
> 3. Return 2–8 objects, the most central first, marking each "primary" (the
>    conjecture is fundamentally about it) or "secondary" (appears in the
>    statement but is not the subject).
> 4. Exclude generic mathematical words — number, function, set, sequence,
>    bound, constant, integer, proof — unless part of a standard compound object
>    (L-function, zeta function, generating function, prime number is fine as
>    "prime").
> 5. Prefer the standard community name over a paraphrase ("partially ordered
>    set" → "poset", "symmetric group" not "permutation group of n letters").
> 6. If the text is not actually a mathematical conjecture, set
>    looks_like_conjecture to false and still extract what objects you can.

**Output schema:**

```json
{
  "objects": [{"name": "string", "qualifier": "string|null",
               "centrality": "primary|secondary"}],
  "looks_like_conjecture": "boolean"
}
```

A `--sync --limit N` flag runs direct API calls for prompt iteration; the full
batch was submitted only after a hand-reviewed dry run.

**Extraction results (actual run):** 1,936/1,936 conjectures extracted (1,935 via
three batches of ≤500; one request expired server-side and was retried
synchronously). Median **4 objects per conjecture** (min 0, max 8); only 4 rows
(0.2%) returned no objects; 123 rows were flagged `looks_like_conjecture: false`
by the extractor (mostly definitions, theorems, or remarks that sit in a
`\begin{conjecture}` environment). Token usage: 280k uncached input + 2.85M
cache-read input (the prompt cache absorbed ~91% of input volume) + 316k output
= **$2.16** at batch + introductory Sonnet 5 pricing.

## 4. Normalization — building the canonical vocabulary

Raw extractions are noisy ("finite poset" vs "poset", "elliptic curves over Q" vs
"elliptic curve"). `scripts/03_normalize.py` canonicalizes in two passes:

**Pass A — mechanical folding (no API).** NFC-normalize, lowercase, strip TeX
remnants and leading articles, collapse whitespace, and singularize the head noun
with a small rule set (`-ies → -y`, `-es`/`-s` stripping) guarded by an exception
list (*series, calculus, genus, modulus, locus, basis, analysis, matrix, vertex,
simplex, …*). Terms are tallied by document frequency into `data/raw_terms.tsv`.

**Pass B — LLM-assisted merge (claude-sonnet-5, ~30 calls).**

1. *Anchor dedup.* Every folded term with document frequency ≥ 3 is an anchor
   candidate. One call merges synonym groups **within** the anchor list
   ("poset" / "partially ordered set"), keeping the most standard name. Distinct
   but related objects ("graph" vs "directed graph") are explicitly not merged.
2. *Tail mapping.* Terms with df < 3 are sent in chunks of 150 with the full
   anchor vocabulary in context. For each, the model returns `map_to <anchor>`,
   `new_canonical` (genuinely distinct object), or `discard` (vague/garbled/not
   an object). `map_to` targets are validated in code — an answer outside the
   anchor list is rejected.
3. *Hierarchy.* Each canonical object is assigned a `parent area` from a fixed
   20-item list mirroring the mathematical fields (combinatorics, number theory,
   algebraic geometry, …) plus an optional more-general `parent_object`
   ("abelian variety" → "algebraic variety").

Review artifacts are written to `data/review_normalize.txt`: the top-50
canonicals, any mega-merge (> 15 aliases), and canonical pairs within edit
distance 2 (missed-merge suspects).

**Normalization results (actual run):** Pass A folded the raw extractions to
**4,252 distinct terms** — 744 anchors (df ≥ 3) and 3,508 tail terms. Pass B
mapped 926 tail terms onto anchors, kept 1,260 as new canonical objects, and
discarded 1,321 as vague or non-objects, yielding **1,977 canonical objects**,
of which **982 appear in ≥ 2 conjectures** (and therefore create edges). Review
flags were clean: zero mega-merges, and every edit-distance-≤2 pair
(graph/digraph, matrix/matroid, cohomology/homology, Cayley graph/Paley graph)
is a genuinely distinct pair that was correctly *not* merged. Top objects by
document frequency: graph (196), prime (63), polynomial (57), vertex (53),
partition (42), generating function (41), chromatic number (40).

## 4b. What we mean by "entity" — a typed vocabulary

Philosophically, a [mathematical object](https://en.wikipedia.org/wiki/Mathematical_object)
is any abstract concept arising in mathematics — numbers, sets, and functions are
the paradigm cases. Our vocabulary is deliberately **narrower** than that (we
exclude the paradigm cases as non-discriminative: nearly every conjecture
involves a number) and **broader** in another direction: following common
practice, we admit unsaturated concepts — properties, relations, and invariants —
alongside saturated objects, but we *type* them rather than flattening
everything into one bag. The typing follows Frege's saturated/unsaturated
distinction:

| type | definition | examples |
|---|---|---|
| `structure` | saturated kind of mathematical thing — you can exhibit an instance | poset, elliptic curve, Cayley graph, matroid |
| `invariant` | quantity/function *of* a structure (implicit argument slot) | chromatic number, genus, Mordell–Weil rank |
| `property` | predicate or relation holding *of* structures | log concavity, isomorphism, density |
| `statement` | named theorem/conjecture/hypothesis referred to as a thing | Riemann hypothesis, Einstein vacuum equations |
| `discarded` | proof techniques & meta-mathematical words — excluded downstream | polynomial method, counterexample, upper bound |

Structures may additionally carry `individual: true` when they name one specific
instance ("Monster group", "Riemann zeta function") rather than a kind.

`scripts/03b_type.py` assigns types to every canonical vocabulary entry
(claude-sonnet-5, chunks of 100 with example conjecture titles as context,
schema-enforced, checkpointed into `vocab.json`). Type distribution and top
entries per type are reported in `data/review_types.txt`.

**Typing results (actual run, full corpus):** all 3,795 vocabulary entries
typed: **2,664 structures, 667 invariants, 194 properties, 195 statements, 75
discarded**; 417 entries flagged as individuals. Spot checks: chromatic
number/girth/eigenvalue → invariant; Tate/Riemann/Hodge conjectures →
individual statements; algorithm/solution/forcing → discarded. With type
weighting applied, total edge weight decomposes as **structure 81%, invariant
16%, property 2%, statement 2%** — properties no longer masquerade as strong
mathematical kinship.

## 5. Graph construction

`scripts/04_graph.py` builds a bipartite conjecture↔object incidence and projects
it to a weighted conjecture–conjecture graph:

- **IDF weighting.** With *N* conjectures and object *o* appearing in *df(o)* of
  them, `idf(o) = ln(N / df(o))`. The edge weight between two conjectures is
  **Σ idf(o)² over their shared objects** — the square makes one shared *rare*
  object (a specific moduli space) count far more than several shared common ones
  ("graph", "prime"). This is what keeps the map from collapsing into a hairball
  around ubiquitous objects.
- **Type weighting.** Each shared entity's idf² contribution is multiplied by a
  type factor: structure ×1.0, statement ×1.5 (two conjectures both invoking the
  Riemann hypothesis is a very strong link), invariant ×0.8, property ×0.4
  (half of mathematics is "isomorphic" to something), discarded ×0 (excluded).
  The script prints the edge-weight composition by type for tuning.
- **Ubiquity cutoff.** Objects appearing in > 15% of conjectures are excluded
  from the projection entirely (they remain as filterable tags on nodes).
- **Pruning.** Keep the union of each node's top-6 edges by weight, then drop the
  bottom quartile of the surviving weights. This keeps the force layout readable.

Each edge records **which** objects it shares, so relatedness is always
explainable in the UI, never a bare similarity score.

**Graph results (actual run, full corpus, with type weighting):** no object
exceeded the 15% ubiquity cutoff, so the IDF² weighting alone tames the common
objects; the 75 `discarded` entities are excluded. Raw projection: 123,821
edges → **12,119 after pruning**. The final graph has 3,952 nodes: a giant
component of 3,476 (**88%**), 332 isolated nodes (8%), and max degree 25.

## 5b. Further annotation stages (merged into the map when present)

**MSC 2020 codes** (`scripts/07_msc.py`). Each conjecture gets 1–2 five-char
MSC 2020 codes (batch job; context = title + statement + the paper's abstract
from the dataset's `papers` config). Codes are validated against the vendored
official taxonomy (`vendor/msc2020.json`, 6,603 codes from
[msc2020.org](https://msc2020.org), CC BY-NC-SA); invalid leaves fall back to
their 3-char class. **Run results: all 3,952 coded, 100% valid, all
five-character primaries.** Top classes match the corpus: 05 combinatorics
(1,050), 11 number theory (703), 14 algebraic geometry (394). The map can color
by MSC top-level class — this also classifies the ~719 nodes with no arXiv
category.

**Embedding clusters** (`scripts/08_clusters.py`). Title + statement embedded
locally (`all-MiniLM-L6-v2`), clustered with HDBSCAN (leaf selection,
min cluster size 5), each cluster named by Claude from its most central
members. **Run results: 208 named clusters covering 1,745 conjectures (44%)**
— the rest are honestly unclustered noise. Examples: "Ramanujan-type pi
series", "hypergraph matching Erdős conjecture", "geometric Langlands
correspondence". The same embeddings yield 379 near-duplicate candidate pairs
(cosine ≥ 0.93) fed to the relations stage.

**Logical relations** (`scripts/09_relations.py`). Candidate pairs = top 6,000
graph edges by weight + the near-duplicate pairs. Each pair is classified
strictly (generalizes / implies / equivalent / same_conjecture / none, with a
justification; "related/analogous" is explicitly `none`). **Run results: 6,076
pairs classified → 701 relations (387 generalizes, 183 same-conjecture, 102
implies, 29 equivalent); 88% none**, which is the intended strictness. Relations
render as violet directional arrows and a per-node panel section with the
justifications.

**Lean/mathlib formalization** (`scripts/10_lean.py`). Every conjecture queried
against [LeanSearch](https://leansearch.net) (rate-limited, cached); hits
prefiltered by embedding similarity to the statement; plausible hits verified
by Claude against a strict standard ("formalizes the statement" vs "related
material"). **Run results — an honest near-null: 3 of 3,952 conjectures have
even a related mathlib hit, and none are statement-formalized.** Research-
frontier conjectures are essentially absent from mathlib. Caveat: LeanSearch
indexes mathlib only — formalizations in standalone Lean repositories (e.g. the
Aharoni–Korman counterexample) are invisible to this check.

**Bridge entities** (`scripts/11_bridges.py` → `reports/bridge_objects.md`).
For each *structure* appearing in ≥ 8 MSC-classified conjectures, the Shannon
entropy of the top-level MSC classes it touches. High df × high entropy = a
field bridge. Top bridges of this corpus: probability distribution, polynomial,
matrix, sphere, field, measure, representation, lattice — the universal
structures of mathematics, empirically.

## 6. Visualization

`templates/viz.html` + `scripts/05_render.py` → `conjecture_map.html`, a single
file with the graph JSON embedded. **Zero external requests** — no CDN scripts,
no fonts, no fetches — so it works offline and under strict CSPs.

- **Rendering:** hand-rolled HTML5 canvas force simulation (spring forces on
  edges, spatial-grid O(n)-per-frame repulsion, mild centering gravity; ~340
  ticks then freeze).
- **Encodings:** color = top-7 arXiv categories + "other" (fixed-order
  colorblind-validated palette, separate light/dark variants selected via
  `prefers-color-scheme`); node radius = √interestingness.
- **LaTeX rendering:** statements render as real math via a **vendored KaTeX**
  (JS + CSS with woff2 fonts inlined as data URIs from `vendor/katex/`, injected
  by `05_render.py` — still zero external requests). The panel renders the
  gently-cleaned `render_tex` (from `body_tex`, math delimiters and environments
  intact) with `throwOnError: false`; author-defined macros the renderer doesn't
  know degrade to visible red TeX source, and rows with no TeX fall back to
  plain text.
- **Interactions:** pan/zoom; hover tooltip; click opens a detail panel with the
  rendered statement, scores, authors, arXiv link, clickable entity chips
  (typed, see § 4b) that filter the map, and the most related conjectures with
  the shared entities that link them; search over titles + entities; category
  legend toggles; open-only toggle; min-interestingness slider; a bipartite
  "show objects" mode with type-shaped entity nodes.
- **Path finding:** with a node selected, shift-click a second node to run
  Dijkstra over inverted edge weights (strong edges are cheap) and highlight the
  shortest-strongest chain connecting them; the panel lists each hop with the
  entities shared across it.
- **Color modes:** color by arXiv category, MSC top-level class, or topic
  cluster (top 7 keys + other in each mode; legend doubles as filter).
- **Ontology browser:** a collapsible tree of the structure vocabulary
  (area → parent structure → structure, with conjecture counts) that drives the
  same entity filter as clicking a chip.
- **Relations & badges:** violet arrows show typed logical relations
  (generalizes/implies/equivalent/restates) with justifications in the panel;
  nodes with mathlib-related material carry a Lean badge linking to the
  declaration's documentation.
- **Shareable URLs:** the selected node and every filter (categories, search,
  open-only, min-interest, entity filter, objects mode) are encoded in
  `location.hash` and restored on load — any view can be sent as a link.

## 7. Limitations & threats to validity

- **LLM extraction noise.** Object lists are model judgments. Spot checks looked
  good, but expect occasional missed objects, over-specific names, or hallucinated
  standardizations. The `centrality` field is heuristic.
- **Normalization merge errors.** Pass B can under-merge (synonyms kept separate
  → a missing edge) or over-merge (distinct objects fused → a spurious edge).
  The review file flags the likely cases but not all of them.
- **Selection bias from licensing.** Only CC-licensed papers contribute text
  (47% of the dataset). If licensing practice correlates with field or country,
  the map's field balance is skewed relative to the full dataset.
- **Upstream label noise.** `real_open_conjecture` labels, interestingness and
  viability scores come from a single model (gpt-5-mini) in the source dataset
  and are inherited unaudited.
- **Restatement dedup is exact-text only.** The same conjecture phrased two
  different ways is not collapsed and will appear as two heavily-linked nodes.

## Proof workspace (interactive theorem proving)

The map doubles as a launcher for an interactive proof workspace: pick a
conjecture (each node panel has a *prove this* button when the local server is
running), or enter any theorem free-form, then develop the proof step by step
while an agent — driven by the `prove-conjecture` skill — checks each step,
gives hints, or takes over delegated subgoals. Every claim is graded
(verified / partially verified / unverified / refuted), every check the agent
runs is an executable script saved with the session, and counterexamples get
the full Lakatos treatment (global/local diagnostic + suggested repair).

```bash
source .venv/bin/activate           # needs: fastapi uvicorn claude-agent-sdk
export ANTHROPIC_API_KEY=…          # or an active `claude` CLI login
uvicorn app.server:app --port 8765
open http://127.0.0.1:8765/workspace         # or /workspace?demo=sqrt2
```

- `/` serves the map (with the *prove this* buttons live).
- `/workspace?demo=sqrt2` is a guided walkthrough of the √2-irrationality
  proof that teaches the interface — including watching the agent catch a
  deliberately unjustified step.
- Sessions persist under `sessions/` and survive server restarts (the agent
  conversation resumes, or falls back to a state recap).
- `PROOF_AGENT_MODEL=claude-sonnet-5` (or another model id) overrides the
  agent model; `PROOF_STUB_AGENT=1` runs a no-API stub for UI development.

**Optional Lean machine-checking.** With a Lean toolchain installed, every
step can additionally be formalized as a Lean 4 lemma checked against a
pinned Mathlib — by hand (a per-step editor compiles your Lean with no LLM
involved) or by the agent (a `lean-formalizer` subagent iterates against the
compiler, and the main agent must affirm the formal statement's faithfulness
before the step earns its *machine-checked* badge). One-time setup:

```bash
brew install elan-init      # Lean version manager (or the official installer)
cd lean && lake exe cache get   # pinned toolchain + prebuilt Mathlib (~5 GB)
```

Without the toolchain everything else works; Lean UI simply stays hidden
(`GET /api/lean/status` reports availability).

---

## 8. Reproducing

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # or `ant auth login`

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
open conjecture_map.html
```

Every stage caches to `data/` and skips completed work: extraction is keyed by
content hash in `extractions.jsonl` (crash-safe append), so interrupting and
rerunning never re-pays for finished calls.

**Actual cost & runtime:** v1 (public text only) ≈ $3.50. The full-corpus
expansion (withheld recovery + extraction delta + MSC + clusters + relations +
Lean verification) added ≈ $20 in API usage ($15.90 of it in half-price
batches, with prompt caching absorbing ~3M input tokens) and ~4 hours of
wall-clock, dominated by arXiv/LeanSearch rate limits and batch queue time.
**Project total ≈ $23.**
