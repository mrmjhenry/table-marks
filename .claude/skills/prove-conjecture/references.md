# References and evidence base for the prove-conjecture skill

Findings from a literature review (July 2026) on structured methodologies for conjecture proving, run to extend the skill beyond its original CERME10 basis. Claims marked **[verified]** survived 3-0 adversarial verification against primary sources; claims marked **[extracted]** come from fetched primary sources but were not independently re-verified.

## 1. CERME10 base model (original skill foundation)

Fernández-León, Toscano-Barragán & Gavilán-Izquierdo, *How mathematicians conjecture and prove* (CERME10 Proceedings, 2017, pp. 2041–2048; PDF in repo root). Case study of a research mathematician. All activity splits into **horizontal mathematising** (informal: experimenting with objects, testing conjectures on examples, harvesting techniques from related proofs) and **vertical mathematising** (formal: stating conjectures from patterns, selecting proof methods, chaining known results, generalizing worked cases). Counterexamples trigger statement modification, not abandonment. Categories C.H.a–c, C.V.a–b (conjecturing) and P.H.a–b, P.V.a–d (proving) are cited throughout SKILL.md.

## 2. Pólya via Newell (1981)

Newell, *The Heuristic of George Polya and its Relation to Artificial Intelligence* (CMU; stacks.stanford.edu/file/druid:gj292yv5713).

- **[verified]** Auxiliary problems dominate Pólya's heuristic: 50% of the core questions and 60% of worked examples in *How to Solve It* involve generating auxiliary problems. Lemma generation should be first-class and frequent.
- **[verified]** Pólya's subproblems are often **wild**: "a subproblem whose use in the main problem is still a problem, even after it is solved" (vs. **tame** subgoals whose use is known at generation time). Integration of a solved lemma back into the main proof is a distinct problem-solving step, and historically the hard one for automation.
- **[verified]** Object-centered search spaces foreclose **proof repair**: "What is lost is the ability to discover a proof by taking an imperfect proof and improving it. Or... to start with a wrong proof (because it is the proof of a different theorem) and to transform it into a good proof." Partial and analogous proofs should be first-class mutable objects, with a transplant-and-repair move.
- **[extracted]** Pólya's four-phase loop (understand / plan / carry out / **look back**) contributes the look-back phase: reflect on what the proof actually needed and what generalizes.

## 3. Lakatos, *Proofs and Refutations* (1976)

Verified against the Cambridge edition frontmatter and Martin & Pease, *Mathematical Practice, Crowdsourcing, and Social Machines* (arXiv:1305.0900). Pease et al. have prior computational operationalizations of these methods.

- **[verified]** Six named responses to a global counterexample: **surrender**, **monster-barring** (redefine the ambiguous concept to exclude the pathological object), **exception-barring** (piecemeal exclusion or strategic withdrawal to a safe domain), **monster-adjustment** (reinterpret the object so it no longer refutes), **lemma-incorporation** (locate the guilty proof step and build its condition into the theorem statement), and the full **method of proofs and refutations**. This is a decision branch, not a single "weaken the statement" move.
- **[verified]** Two-axis counterexample diagnostic: global (refutes the conjecture) × local (refutes a specific proof step). *Local-but-not-global* → repair the step, conjecture survives. *Global-but-not-local* → a hidden lemma exists; make implicit assumptions explicit, then lemma-incorporate.
- **[verified]** **Proof-generated concepts** (case studies: uniform convergence, bounded variation, Carathéodory measurability): after a proof attempt, the conditions the proof actually used may define a better concept than the naive one in the statement. Distinct from narrowing the statement — it redefines the objects.
- **[extracted]** The overall Lakatosian pipeline: naive conjecture → naive proof + proof analysis under criticism → proof-generated formal theory. Formalization is itself a discovery mechanism; sometimes the right formal frame must be constructed, not assumed.

## 4. Empirical effort distribution (Martin & Pease 2013, arXiv:1305.0900)

- **[verified, medium confidence]** In mini-polymath 3 only 24% of the 174 comments formed the final proof; examples were 33%, conjectures 20%, concept formation 10%. In MathOverflow responses, 34% used explicit examples as evidence/counterexamples and 56% cited literature — often **extracting consequences not explicit in the cited paper**. Caveats: n=1 competition problem; preliminary MO sample. Implication: budget most effort to example exploration, sub-conjecturing, and literature mining for implicit corollaries.

## 5. Gowers' human-oriented ATP programme

Sources: gowers.wordpress.com (2022 announcement), wtgowers.github.io/human-style-atp, Ganesalingam & Gowers, *A fully automatic theorem prover with human-style output* (J. Automated Reasoning, 2017).

- **[verified]** **No brute-force search** as a design constraint: "searches will be strongly discouraged unless human mathematicians would also need to do them." Humans prune so effectively that little backtracking is needed; a large feasible search is a design failure, not a fallback.
- **[verified]** **Motivated proofs / proof justifications**: every step should carry a plausible account of how someone could have had the idea — "a proof that does not involve rabbits being drawn out of hats." No formal definition exists; it is a heuristic standard.
- **[verified]** A codified move set for routine proving: Boyer-Moore-style **waterfall** (deletion tactics → tidying → forwards/backwards/library reasoning → metavariable creation, always the first applicable), **lazy definition expansion** (don't unfold unless higher-level moves are checked unavailable), no CNF conversion, no backtracking on routine problems. Human-readable proofs cannot be recovered by post-processing machine-oriented prover output — the moves themselves must mirror human reasoning.

## 6. Thurston, *On Proof and Progress in Mathematics* (Bull. AMS, 1994)

- **[verified]** Hierarchical decomposition: mathematicians break proofs into intermediate results "so that they don't have to hold too much logic at once."
- **[verified]** Idea-level weakness hunting is distinct from formal checking: "People are usually not very good in checking formal correctness of proofs, but they are quite good at detecting potential weaknesses or flaws in proofs." Both passes are needed; neither substitutes for the other.
- **[verified]** His geometrization workflow: years building a repertoire of constructions/examples/proofs → conjecture → proof (Haken case) → deliberate adversarial phase "checking the proof, searching for difficulties and testing it against independent information."

## 7. Modern AI-prover practice

- **[verified]** **Draft-Sketch-Prove** (Jiang et al., ICLR 2023, arXiv:2210.12283): (1) informal proof draft → (2) formal sketch mirroring the informal steps, with open subgoals → (3) close subgoals with automated tools. Sketch guidance raised Isabelle miniF2F success 20.9% → 39.3%. Durable lesson: hierarchical informal-to-formal decomposition beats direct search. Extended by LEGO-Prover, SubgoalXL.
- **[verified, medium — 2026 preprint]** **Agentic Researcher** (Zimmer, Pelleriti, Roux, Pokutta, arXiv:2603.15914): (a) **counterexample-first reasoning** — before any proof attempt, actively search for counterexamples (randomized inputs, boundary cases, exhaustive small-instance enumeration): a counterexample search finds failures faster than a failed proof reveals the obstruction, and a *surviving* search often exposes the structural property that makes the proof work; (b) **grade every claim** verified / partially verified / unverified, with executable verification scripts rather than prose — this caught concrete derivation errors (a missing factor of two) before further argument was built on them.
- **[extracted]** **LEGO-Prover** (arXiv:2310.00656): grow a library of verified lemmas across problems; record failed lemma statements as open requests; reject proofs containing escape hatches (`sorry`).
- **[extracted]** **Critic-model triage** (arXiv:2410.15700): score unproven statements for tractability and spend budget on the most promising first.
- **[extracted]** Autoformalization discipline: type-checking ≠ semantic faithfulness — a compiled formal statement can misstate the theorem, so a separate semantic-equivalence check is required; **hypothesis rejection** — attempt to prove the *negation* of a formalized conjecture as a falsification filter.

## 8. Machine conjecturing

- **[extracted]** Davies et al., *Advancing mathematics by guiding human intuition with AI* (Nature 2021): the **learnability gate** — before investing proof effort in a suspected relationship X→Y, train a supervised model; above-chance accuracy (78% vs 25% baseline in the knot signature case) establishes the relationship is real, and gradient attribution identifies *which* input features drive it, guiding what to prove. Ran end-to-end to a new proved theorem (natural slope vs. signature bound).
- **[extracted]** Ramanujan Machine (Nature 2021): numerics-first conjecture mining (enumeration + numerical matching) precedes proof entirely; rediscovers known formulas as sanity checks alongside novel ones.
- **[extracted]** Tao's PFR and Equational Theories projects: the **Blueprint** pattern — a human-readable proof document linked to the Lean formalization, auto-generating a lemma dependency graph color-coded by status — as a mechanism for tracking hierarchical decomposition and choosing the next actionable node.

## 9. Structured proofs and proof validation

- **[extracted]** Lamport, *How to Write a 21st Century Proof*: hierarchical numbered proofs where every step names its justification and every (sub)proof must end by stating exactly its goal — a mechanical check that catches proofs which never establish what they claim; structured rewriting re-exposed a known error in a published Schroeder-Bernstein proof.
- **[extracted]** Weber & Mejia-Ramos line (Educ. Studies in Math.): mathematicians validate proofs by **instantiating individual proof steps on concrete examples** (a per-step sanity check), and reading-to-comprehend vs refereeing are distinct activities — supporting separate technique-harvesting and adversarial-verification reading modes.
- **[extracted]** Lockwood, Ellis & Knuth: taxonomy of example **types, uses, and strategies**, distinguishing example use during conjecture formulation from example use during proving.

## Open questions from the review

1. How to operationalize wild-subproblem integration — what moves turn a solved auxiliary lemma into progress on the main problem?
2. Can "proof justification" be made checkable rather than heuristic?
3. Do the Polymath/MathOverflow effort distributions transfer to research-level open conjectures?
4. Which Lakatosian repair operations can be reliably automated, and what is the decision policy among them?
