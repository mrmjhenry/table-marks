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
openconjecture_data_dictionary.pdf   data dictionary for the source dataset
ROADMAP.md                           planned improvements (LaTeX rendering, proof
                                     linking, MSC/topic classification, …)
data/                                gitignored — cached pipeline intermediates
                                     (extractions, vocabulary, graph). Kept local
                                     partly for licensing reasons: derived text
                                     from arXiv papers should not be republished
                                     beyond what the source dataset permits.
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

**Filtering decisions** (`scripts/01_fetch.py`):

- **Public text only.** 2,181 rows (53%) have `text_withheld = true` — their text
  is not republishable because the source paper is under arXiv's
  non-exclusive-distribution license. We keep the 1,966 rows with text (their
  papers are CC-licensed). This is a *selection bias*: CC-licensing practices vary
  by community, so fields are not represented proportionally (see § Limitations).
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

Pipeline row counts from the actual run:

| stage | rows |
|---|---|
| dataset total | 4,147 |
| with public text | 1,966 |
| non-empty after cleaning | 1,964 |
| after dedup | **1,936** |
| labeled `real_open_conjecture` | 1,596 |

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

**Typing results (actual run):** all 1,977 entries typed in 20 calls (~$0.40):
**1,418 structures, 359 invariants, 98 properties, 72 statements, 30
discarded**; 206 entries flagged as individuals. Spot checks: chromatic
number/girth/eigenvalue → invariant; Tate/Riemann/Hodge conjectures →
individual statements; algorithm/solution/forcing → discarded. With type
weighting applied, total edge weight decomposes as **structure 83%, invariant
14%, property 2%, statement 1%** — properties no longer masquerade as strong
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

**Graph results (actual run, with type weighting):** no object exceeded the 15%
ubiquity cutoff (the most common, "graph", sits at 10%), so the IDF² weighting
alone tames the common objects; the 30 `discarded` entities are excluded. Raw
projection: 47,097 edges → **5,604 after pruning**. The final graph has 1,936
nodes: a giant component of 1,629 (**84%**), 197 isolated nodes (10%), and max
degree 19.

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
- **Interactions:** pan/zoom; hover tooltip; click opens a detail panel with the
  statement (raw TeX shown as text), scores, authors, arXiv link, clickable
  object chips that filter the map, and the most related conjectures with the
  shared objects that link them; search over titles + objects; category legend
  toggles; open-only toggle; min-interestingness slider; a bipartite "show
  objects" mode that adds object nodes (squares, sized by frequency) and re-runs
  the layout.

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

## 8. Reproducing

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # or `ant auth login`

python scripts/01_fetch.py                     # ~1 min, downloads the dataset
python scripts/02_extract.py --sync --limit 20 # review extraction quality first
python scripts/02_extract.py                   # full batch; resumable, polls until done
python scripts/03_normalize.py                 # ~30 LLM calls
python scripts/04_graph.py                     # local only
python scripts/05_render.py                    # → conjecture_map.html
open conjecture_map.html
```

Every stage caches to `data/` and skips completed work: extraction is keyed by
content hash in `extractions.jsonl` (crash-safe append), so interrupting and
rerunning never re-pays for finished calls.

**Actual cost & runtime of this run:** extraction $2.16 (three batches,
~50 minutes wall-clock, dominated by batch queue time); normalization ~40
synchronous calls (~$1, ~4 minutes); everything else is local and takes seconds.
**Total ≈ $3–3.50.**
