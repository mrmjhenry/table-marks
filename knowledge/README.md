# Field knowledge base

A cross-session store of proof approaches, techniques, and assumptions the
workspace agent accumulates, keyed by MSC 2020 field. It is a **committed
repo asset**: entries arrive as ordinary git diffs, so curation is code
review — edit or delete entries freely; the app treats these files as the
source of truth.

## Layout

One JSON file per MSC **subclass** (e.g. `11Bxx.json` holds the subclass and
every leaf under it, such as `11B25`), plus `NN-XX.json` for class-level
entries. Files exist only for fields that have been encountered.

## Entry schema

```jsonc
{
  "id": "11Bxx-k007",             // file code + per-file counter
  "code": "11B25",                // exact MSC code (may be a leaf)
  "kind": "technique",            // technique | assumption | pitfall | lemma
                                  //   | counterexample_pattern | literature
  "title": "Density increment on long APs",
  "body": "one short paragraph; markdown + $LaTeX$ welcome",
  "refinement": "Szemerédi-type density arguments",   // free sub-field tag
  "provenance": {
    "origin": "session",          // session | seeded | theoremsearch
    "session_ids": ["s_…"],       // sessions that contributed/confirmed
    "status": "verified"          // verified | recalled_unverified | cited
  },
  "created": "…", "updated": "…"
}
```

Provenance semantics: `session` entries record what an actual proof
established (look-back); `seeded` entries are agent-recalled playbook
material — treat as unverified citations until checked; `theoremsearch`
entries cache literature hits. The workspace injects a capped, hierarchy-
walked selection (leaf → subclass → class) into each session's context and
exposes `query_knowledge` for on-demand lookups.
