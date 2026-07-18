# Documented failure modes and their countermeasures

The catalog of ways LLM-assisted proving goes wrong, drawn from the 2024–2026 record (`evidence-base.md` §10). Each entry: the failure, why it happens, and the countermeasure the skill enforces. Load this during verification, or when a proof "feels done" — that feeling is when several of these fire.

### Reference fabrication
The single most common documented failure in LLM mathematical writing: citing a theorem, paper, or named result that does not exist, or that does not say what it is quoted as saying. It happens because a plausible-sounding citation is cheap to generate and rarely challenged. **Countermeasure:** every external citation carries its exact statement-as-used, its source, and a note on whether the source was actually consulted this session or recalled from training memory. Recalled citations are marked `[UNVERIFIED-CITATION]` until checked. A cited result is only usable after its hypotheses are checked in the current setting.

### Already-solved "open" problems (novelty failure)
AI systems have announced solutions to problems that were settled decades earlier under different terminology; ~2.5% of withdrawn arXiv math preprints duplicate prior results (Gemini/Erdős case, 2601.22401). The model's training memory is not a reliable index of what is already known. **Countermeasure:** the Phase 0 **novelty gate** — never assert a claim is new without a recorded literature search, and record the search terms. Classify the claim as (a) known result to re-derive, (b) plausibly new, (c) open/conjectural, and let that set the downstream burden.

### Inequality-direction and constant-tracking errors
The most common defect class that *survives* into final proofs (FirstProof, 2602.05192): a flipped `≤`, a dropped factor of two, a constant that changes value between two lines, a limit and a sum silently exchanged. These are invisible to prose review because the surrounding argument reads fluently. **Countermeasure:** numeric spot checks on the final proof (`verification-protocol.md` check 4) — every quantitative claim gets an executable check with a seed, run against the *final* text, not just the exploration.

### Wishful verification
"Verifying" a proof by re-reading it and finding it convincing — which measures fluency, not correctness. The prover is the worst-placed party to catch its own gaps. **Countermeasure:** step-level audit over holistic review, and independent **clean-context** re-derivation that never sees the prover's reasoning or confidence. "It looks correct" is not a verification verdict.

### Circular verification
A verifier that shares the prover's context, assumptions, or unstated lemmas will bless exactly the errors the prover made — the verification is correlated with the thing it checks and adds no information. **Countermeasure:** the anti-circularity principle — strip the verifier's context to statement + proof only; run multiple adversarial rounds; use a different model family for a round when available (oracle Tier 3). Errors survived to rounds 2 and 5 in the Kochen–Specker workflow (2603.16988); one clean round is not enough.

### Context-degradation drift in long proofs
Over a long session, the working state held in conversation context degrades: a lemma's exact statement blurs, an earlier assumption is quietly dropped, two subtly different objects merge. The proof becomes internally inconsistent without any single visible error. **Countermeasure:** **files are the source of truth.** Once a lemma passes verification, persist its exact statement and proof to a file and **lock** it — treat it as immutable unless a downstream contradiction forces an explicit reopening. Do not rely on conversation memory for anything load-bearing.

### Pressure-induced confabulation
Asked to produce a *complete* proof, the model invents the missing step rather than reporting the gap — the completeness request manufactures the fabrication. This is the failure the entire verification apparatus exists to catch, so do not generate it in the first place. **Countermeasure:** a known gap is stated explicitly with a `[GAP]` marker and a description of what would close it. A partial proof honestly labeled is a result; a complete-looking proof with an invented step is a liability. Never present a proof with a known gap as complete.
