# Λεξόραμα — Deletion Review (Decision Record)

**Supersedes** `docs/REDESIGN.md` §10 Phase 1 ("The deletion PR") and §3.5 ("Deleted outright").
**Date** 2026-07-22 · **Branch** `audit-remediation` · **DB re-measured this session** against
`data/db/lexorama.sqlite` (read-only, COUNT/LIMIT only).
**Evidence base** `docs/AUDIT.md` (63 findings), `docs/PRODUCT-REVIEW.md` §4–5, `docs/REDESIGN.md`
§3.5/§6/§10, `BACKLOG.md` (methodology waves #43–#51, decisions D1–D6). Per-item preliminary
analysis, an adversarial cut-vs-keep debate, and an independent judge's ruling stand behind each row.

This record does not restate the deletion PR. It overturns it. Net result across the nine items the
PR proposed to delete: **0 clean deletions**. Six FIX, two REPLACE (the two genuine encoding/
architecture cuts), one DEFER.

---

## 1. The reframe, stated once

The maintainer has defined the project verbatim: *"not a for-profit, or an openly distributed
project. It's a research project on dictionary building and word-meaning shift over greek corpora
and greek-english translations."* The three research questions:

- **RQ1 — dictionary building.** Constructing a form→lemma, sourced, structured Greek dictionary.
- **RQ2 — word-meaning shift over Greek corpora.** Diachronic lexical semantics.
- **RQ3 — Greek↔English translation.**

The deletion PR inherited its objective from `docs/PRODUCT-REVIEW.md`, whose thesis is "a Greek
speaker with a lookup task." Under that thesis, every surface that does not serve a casual lookup is
overhead to be deleted. The reframe voids that thesis: **the researcher is the user**, so
"not enough users to justify the maintenance cost" is not a valid argument, and the corpus/
diachronic layer is the research *core*, not feature accretion.

Two distinctions govern every ruling below and must never be collapsed:

- **BROKEN ≠ SHOULD-BE-DELETED.** The audit proved many of these features are *broken* (drift is
  ~96% estimator noise, F7/F12; change-points are a corpus-gap artefact, F5/F9; the graph is 63.5%
  untyped `related` edges, F33). Brokenness is about correctness and is framing-independent. For a
  *research* project a broken methodology is the research agenda (waves #43–#51 / decision D3) — a
  reason to **recalibrate the instrument**, not to delete the study. The exception is anything
  **wrong-by-design** (a visual encoding that fails even executed perfectly), which can still be cut.
- **DATA ≠ RENDERING.** Almost every item splits into a data/analysis layer and a rendering layer
  with independent verdicts. Tellingly, the deletion PR already concedes this: `REDESIGN.md:456-457`
  — *"Tables stay in the DB… Deleting a surface from the product is not deleting data from the
  dataset."* On its own terms the PR is a **surface** deletion. The real disagreement therefore
  collapses to two questions: (a) keep or delete the API **endpoints** that carry the statistical
  apparatus, and (b) keep or replace the **visuals**. The reframe answers (a) keep-and-recalibrate,
  and (b) agrees with the PR for the two wrong-by-design encodings and disagrees for the rest.

### Which PR arguments survive the reframe, and which die

**Die:**

- *"Nobody clearly / Nobody"* consumer-reach verdicts (`PRODUCT-REVIEW.md:306-307`). The researcher
  is the user.
- *Coverage-cost deletion rationales* — descendants "0.1%" (`REDESIGN.md:449`), neighbors "13.0% of
  content lemmas" (`:448`). Coverage-cost is the exact argument the reframe disqualifies.
- *"Drift is ~96% estimator noise… change points are a corpus-gap artefact"* as grounds to delete
  ExplorePage/DiachronicPanel (`:446-447`). This is **brokenness**, which under the reframe is a
  reason to FIX (waves #43/#44/#48/#50, D3), not delete.
- *The `ρ=0.79` charge against `semantic_neighbors`* (`:448`). It is **misattributed**: ρ=0.79 is
  F13/C6's property of the *diachronic* `neighbor_overlap` column (`main.py:1062`), a different
  table; the static near-synonym table has no drift value to correlate against.
- *"Domain chips… 0.56 accuracy; 61.0% below CONF_FLOOR"* (`:451`). **Mis-scoped**: the word-page
  chips render *gold* Wiktionary subject tags (`senses.tags`), not classifier output. The number
  describes a different, Explore-only surface.

**Survive (framing-independent, correctness/encoding):**

- *RelationGraph's node-link canvas is the wrong encoding.* 86.2% of lemmas have zero edges, median
  2, only 1.42% reach ≥10 (F34, `AUDIT.md:510-514`). A node-link diagram earns its cost only over a
  text list when there are multi-hop paths to trace; a radius-1 ego star has none. True even with
  perfect data → **REPLACE**.
- *The three viewport-branched JSX trees are an architecture defect.* Three JS-media-query-gated
  navigations are a WCAG 3.2.3/3.2.4 consistency liability; the mobile tab strip is a non-semantic
  `<div>` of `<button>`s (WCAG 1.3.1 failure, F34) → **REPLACE**.
- *Drop `cytoscape` (438,616 B, 55% of the JS bundle).* Survives as a consequence of replacing the
  canvas.
- *The false / overclaiming UI labels* — a hard «καμπή {year}» printed over a NULL change-point
  score, a σημαντική chip with no null distribution, an uncalibrated «εμπιστοσύνη N%», an
  «ομοιότητα X%» that implies meaning-identity. Survive as **honesty fixes** — and they *are* this
  branch's own Phase-0 mission, "stop shipping claims the data contradicts."
- *The card-hierarchy critique* (descendants "ranked visually equal to «Ορισμοί»"; five relation
  cards should merge). Survives as a **re-render / demotion**, not a deletion.

---

## 2. Decision matrix

Ground truth (verified live this session): lemmas **463,411** (content **111,256**; names
**352,155** = 76.0%); forms **2,829,521**; senses **541,759**; relations **294,040**; etymons
**57,790** over **42,751** lemmas. **All nine corpus/Tier-B tables are 0 rows**: `descendants`,
`semantic_neighbors`, `collocations`, `corpus_examples`, `diachronic_drift`,
`diachronic_trajectory`, `diachronic_neighbors`, `frequency_timeseries`, `lemma_domain_pred`.

| # | Item | Serves | Broken vs Wrong | Data | Rendering | **Overall** | Effort | Conf. |
|---|------|--------|-----------------|------|-----------|-------------|--------|-------|
| 1 | ExplorePage (trends/keyness/drift/by-field/compare) | RQ2, RQ1 | Broken (calibration + empty) | FIX | KEEP | **FIX** | L | High |
| 2 | DiachronicPanel (per-word) | RQ2, (RQ1) | Broken; change-point wrong-*as-rendered* | FIX | KEEP + 2 gates | **FIX** | L | High |
| 3 | RelationGraph (Cytoscape) + `/graph` | RQ1 | Data broken-fixable; **encoding wrong-by-design** | KEEP+FIX | **REPLACE** | **REPLACE** | M | High |
| 4 | EntryDescendants + table + pass | RQ1 (weak) | Broken (empty; **no correctness finding**) | KEEP | REPLACE later | **DEFER** | S | High |
| 5 | EntryNeighbors + `semantic_neighbors` | RQ1, RQ2 | Broken (empty; calibration) | KEEP+FIX | REPLACE/DEFER card | **FIX** | S | High |
| 6 | EntryCognates (Ομόρριζες) | RQ1 | Broken-fixable (inherited F57 noise) | KEEP+FIX | KEEP | **FIX** | S | High |
| 7 | Domain chips + `lemma_domain_pred` | RQ1, RQ2 | Gold layer **not broken**; classifier broken-fixable | KEEP gold / DEFER clf | KEEP chips / REPLACE conf% | **FIX** | L | High |
| 8 | Mobile tab strip + 3 viewport trees | none | **Wrong-by-design** (a11y + arch) | n/a | **REPLACE** | **REPLACE** | M | High |
| 9 | ~8 explore/diachronic route handlers | RQ1, RQ2 | Broken (empty + calibration); `word_graph` live | KEEP+FIX | split | **FIX** | L | High |

Effort scale = ideal focused days for one maintainer (same unit as `AUDIT.md §5`). "L" is dominated
by the shared XL diachronic-pipeline rewrite + 8–10 h Tier B rebuild, not by the per-item edits.

---

## 3. Per-item reasoning

### 1 · ExplorePage — corpus trends / keyness / drift-movers / by-field / compare
`apps/web/src/pages/ExplorePage.tsx` (541 LOC); handlers `main.py:1046-1560`. **Verdict: FIX (L).**

- **Strongest keep:** ExplorePage is the primary rendering surface for RQ2 — trends, drift,
  change-point, keyness, cross-corpus compare *are* diachronic lexical semantics; keyness/trends
  also feed RQ1's distinctive-vocabulary extraction. Every defect (F7/F10/F12/F13/F43) lives in the
  data/analysis layer, each with a queued, literature-grounded fix (#45/#46/#43/#48/#50). The
  rendering is correct-by-design and the copy is already honest: Theil–Sen named at
  `ExplorePage.tsx:364`, Mann–Kendall + Benjamini–Hochberg at `:393`, within-corpus percentile ranks
  at `:411-427` — the compare quadrant is the one Explore surface the audit calls defensibly
  designed.
- **Strongest cut:** it is a presentation layer for a research output that does not yet exist — all
  six Tier-B tables are 0 rows (verified), and by the audit's own account every number they will
  hold is a known artefact (keyness G²≥10.83 passes 88.4% of 30,610 candidates with no
  multiple-testing correction, F43; drift ~96% estimator noise, F7/F12). The true RQ2 deliverable is
  a *validated estimator*, established offline in a permutation-null/bootstrap harness, not in a live
  SPA whose API contract every one of waves #43–#51 will churn.
- **Why FIX:** the cut argument's force is *sequencing*, not deletion — don't ship empty panels,
  don't stand behind known-wrong numbers. That is answered by **gating population**, not by
  discarding 541 LOC of correct rendering. `explore_cache` (`main.py:146`) confirms trends/compare
  are deterministic functions of Tier B, so panels can light up per-wave. Deleting the instrument to
  avoid recalibrating it is precisely the research. Conditions: gate each panel behind its wave
  (trends #45, keyness #46, drift-movers #43/#48/#50 **plus** an explicit D3 go/no-go);
  **drop by-field** (`main.py:1289`) until classifier #47 lands — it compounds an unevaluated
  classifier with an unevaluated trend; render an honest "pending recalibration" empty state
  (fix the `setData(null)` error-swallow at `:353`); minor a11y now (enlarge the 2.5 px scatter
  targets; replace the full-reload `<a href>` at `:441` with SPA nav).

### 2 · DiachronicPanel — per-word diachronic panel
`apps/web/src/components/DiachronicPanel.tsx` (375 LOC); `GET /api/word/{lemma}/diachronic`
(`main.py:945-1043`). **Verdict: FIX (L).**

- **Strongest keep:** its four surfaces — frequency-over-time, drift trajectory, change-point,
  then/now neighbours — literally *are* "word-meaning shift over Greek corpora." Under the reframe
  "serves none" is indefensible. The inline-SVG line charts (`DiachronicPanel.tsx:56-178`) are the
  correct, dependency-free, accessible encoding (`role="img"`, per-point `<title>`) — unlike
  RelationGraph there is nothing wrong-by-design to replace.
- **Strongest cut:** every RQ2 *validity* property lives at the aggregate level, yet the panel
  reifies the noisiest cell of the estimator — one lemma's first↔last drift, ringed change-point,
  σημαντική chip — as a per-word fact, at exactly the altitude where a reader most over-reads a
  single high-variance, frequency-confounded (ρ=−0.547, F13) number as settled truth. This
  *survives full recalibration*: a K=100 BCa interval on one lemma is still one draw from a
  high-variance estimator.
- **Why FIX:** the cut insight is real but argues for **honest uncertainty display**, not deletion —
  and the panel already carries CIs (`:206-209`). Once #43 supplies a K≥100 null and #44 a real
  change-point null, a wide band *is* legible per-word uncertainty. Routing everything through the
  aggregate Explore surfaces escapes nothing: the same confound taints the mover tables too. Two
  honesty gates are mandatory and cheap (Phase 0, no Tier-B dependency): **suppress «καμπή ~{year}»
  and the ringed marker while `change_point_score IS NULL`** (render site `DiachronicPanel.tsx:228-236`;
  the Phase-0 gate is `main.py:957`) — currently a hard historical claim printed over a score that is
  NULL in 100% of the old 20,265 rows, with 82.6% of news words collapsing to 2016, the first slice
  after a 3-year corpus hole (F5/F9); and **hide the σημαντική/μη-σημαντική chip** (`:211-226`) until
  F8's permutation null exists. Never render a bare per-word drift point without its CI. The panel is
  inert today (returns null, `:311-317`), so there is no urgency and no harm in leaving the component
  in place until Tier B is rebuilt.

### 3 · RelationGraph (Cytoscape node-link graph) + `GET /api/word/{lemma}/graph`
`apps/web/src/components/RelationGraph.tsx` (242 LOC); `main.py:574-658`. **Verdict: REPLACE (M).**

This is the textbook data≠rendering split — the two advocates are not in conflict; one rules on the
visual, the other on the data.

- **Strongest keep (data):** the deletion PR would also delete `GET /api/word/{lemma}/graph` and its
  tables, but that endpoint is the only surface for Lexorama's structured relational layer —
  verified live: **107,311 typed, per-edge-sourced relations** (synonym 55,911, hypernym 16,322,
  hyponym 16,235, antonym 11,036, derived 7,807) plus **57,790 etymons over 42,751 lemmas**, all
  Tier-A and populated **now** (not the empty-Tier-B case, so DEFER cannot apply). 30,975 content
  lemmas carry a non-`related` typed edge. This is exactly the form→lemma-plus-typed-relations
  lexicon RQ1 is about (OntoLex-Lemon-shaped), hand-assembled from three independent sources —
  slow and licence-encumbered to rebuild.
- **Strongest cut (rendering):** the Cytoscape canvas is wrong-by-design. F34: verified median 2
  edges/lemma, 86.2% zero edges, only 1.42% ≥10 — a radius-1 ego star with no paths, and path-finding
  is the *sole* advantage of node-link over a text list or matrix. F53: one canvas fuses lexical,
  taxonomic and etymological relation families by hue alone in 43.5% of graphs — actively
  misleading. The sourced edges are already carried losslessly, with resolved links, per-edge
  provenance, and keyboard/screen-reader access the bare canvas lacks, by the existing typed-list
  components. The 438,616 B dependency buys nothing.
- **Why REPLACE (not FIX, not CUT):** fixing tooltips (F33: 63.5% of edges are the untyped `related`
  the UI claims to exclude; provenance is written to a `data.title` the canvas never draws) cannot
  cure an encoding with nothing to encode. So REPLACE the rendering: delete the canvas + `cytoscape`
  + `@types/cytoscape`; make typed text lists (`SynonymBlock`/`WordFamily`/`EntryFamily`, which
  already exist) the primary relations UI; route `EntryFamily` into the mobile «Σχέσεις» tab (which
  today has zero accessible content, F34); show etymology as an ordered lineage path, not a hairball.
  Optionally add the redesign's ~120 LOC inline-SVG ego view gated at ≥8 edges (~8.8k lemmas) with
  `role="img"` + `aria-label` + table fallback (`REDESIGN.md:1008-1017`). **KEEP the endpoint and
  tables.** The rendering swap is *not* gated on anything. The F53/F33 data recalibration
  (sense-anchor the omw is-a edges, add `synset_id`/emit only for monosemous sources, drop the 452
  A↔B contradictions and the ~2× mirrored double-count, demote `related` out of the typed-edge
  claim) is a separate L methodology wave — the research — and must **not** gate deleting the wrong
  visual.

### 4 · EntryDescendants card + `descendants` table + `--descendants-only` pass
`apps/web/src/pages/WordPage.tsx:384-405`; `main.py:505-546`; `schema.sql:115-126`;
`ingest_kaikki.py:689-742, 971-1015`. **Verdict: DEFER (S).**

- **Strongest keep:** it is the **only** deletion item with zero correctness findings. F54 and
  CUT-list #1 (`AUDIT.md:530, 1031`) attack only 0.4% coverage and maintenance surface — the exact
  "cost not justified" argument the reframe disqualifies. The data is a correct, sourced,
  provenance-carrying forward-etymology layer, the structural mirror of the 57,790-row etymons, empty
  only because the schema-v2 rebuild omitted a cheap standalone pass (not even in `manifest.py`'s
  owners map; `--descendants-only` is fully wired). Re-population is an S-effort, minutes-long re-run
  over `data/raw/en-extract.jsonl` (already on disk, already sourcing etymons — **no new licensing
  entanglement, no Tier B/word2vec dependency**). The card already no-ops when empty
  (`WordPage.tsx:385`).
- **Strongest cut:** its semantic direction points *out of* every stated RQ. RQ1 needs *backward*
  etymology (served by etymons); descendants record where a Greek word *went* — a fact about other
  languages' lexicons. RQ2 (in-corpus shift) is untouched by cross-language borrowing. RQ3 collapses
  on inspection: verified 50/849 (5.9%) English targets, and the top one (Ελλάδα→"Ellada",
  raw_tag "borrowed") is a transliterated exonym, the opposite of a translation pair. What the layer
  actually is — 610/849 (72%) Aromanian/Romanian/Ottoman-Turkish/Albanian/Bulgarian, i.e. Balkan
  sprachbund contact data — is a legitimate but **undeclared fourth research object**.
- **Why DEFER:** the two advocates are not opposed — keep says "don't cut," cut says "don't invest."
  DEFER is the synthesis. Destroying working, licence-clean infrastructure to save a non-cost is the
  product move the reframe rejects; but spending cycles repopulating/redesigning a layer that serves
  the stated RQs least is equally wrong. Keep the code and the no-op card as-is; do **not** repopulate
  or redesign until a forward-etymology / contact-linguistics research question (a candidate RQ4) is
  actually posed. When re-enabled, REPLACE the full-width card (`REDESIGN.md:449`) with a compact
  entry in a merged «Σχετικές λέξεις» relations module.

### 5 · EntryNeighbors card + `semantic_neighbors` table + `ingest_neighbors` pipeline
`apps/web/src/pages/WordPage.tsx:493-517`; `schema.sql:179-188`; `ingest_neighbors.py`.
**Verdict: FIX (S).**

- **Strongest keep:** a sourced, lemma-linked distributional-synonym layer serving RQ1 twice — as a
  dictionary-building candidate generator *and* as an evaluation target (does cosine recover
  dictionary-attested synonyms?). Its only live defect is 0 rows pending Tier B, identical to the
  rest of the empty corpus layer, and the word2vec pass is the *cheap, non-bootstrap* part of that
  rebuild, which reruns anyway → near-zero marginal cost. Residual issues are one-line: F37
  `pos!='name'` filter (`AUDIT.md:574`), and `seed=`/`workers=1` for reproducibility
  (`ingest_neighbors.py:96`).
- **Strongest cut:** the table has exactly one reader — the `EntryNeighbors` payload
  (`main.py:528`) — and the redesign deletes that card. Grep confirms the diachronic drift
  instrument computes its own `neighbor_overlap` self-containedly (`ingest_diachronic.py:418-552`)
  and never touches this table. So once the card goes, table + 199-LOC pipeline look like dead code
  whose only surface was an overclaiming «ομοιότητα X%» / «Σημασιολογικοί γείτονες» list built on a
  CBOW model that ranks antonyms and co-hyponyms (καλός~κακός) as top neighbours.
- **Why FIX:** the keep rests on RQ1, not the RQ2 "baseline" role (which the cut correctly shows no
  code realizes — the "static precursor to Layer C" at `ingest_neighbors.py:3` is an unrealized
  docstring). But an offline research asset needs no served card to have value, and the `ρ=0.79`
  "duplicates drift" charge is **misattributed** to it (it describes the diachronic
  `neighbor_overlap` column). Tellingly the redesign itself keeps the table "as an internal
  diagnostic" (§3.5) and only drops the card + API field. So: **KEEP+FIX the data** (F37 filter,
  seed/workers=1, add tests; regenerate on the rebuild that reruns word2vec anyway) and **DROP or
  relabel** the consumer card to "context-similar words (distributional)" — dropping the
  meaning-identity implication. Do **not** delete the table or pipeline.

### 6 · EntryCognates card (Ομόρριζες λέξεις)
`apps/web/src/pages/WordPage.tsx:412-446`; `main.py:445-474`; index `schema.sql:98`.
**Verdict: FIX (S).**

- **Strongest keep:** the one deletion-list item needing **neither a Tier B rebuild nor the CC BY-NC
  Leipzig corpus** — a live, index-backed self-join over the etymons table already in the Tier A DB
  (57,790 rows / 42,751 lemmas verified now, vs 0 in descendants and every other Tier-B-blocked panel
  it was wrongly bundled with). A same-root word-family cross-reference derived and source-tagged from
  a structured etymology field is textbook dictionary apparatus (RQ1), already in the reframe-endorsed
  encoding — a grouped sourced chip list, not the F33/F34 hairball. Coverage is real: 43.8% of
  with-etymon content lemmas get a non-empty panel; 80.6% of a 676-edge sample anchor on defensible
  Greek-stage roots.
- **Strongest cut:** over the *unaudited* F57 etymon table it publishes demonstrably false
  equivalences under a source badge — αλφάβητο←ἄλφα (a constituent letter as ancestor); λόγος→ελίτ/
  λεζάντα (deep-PIE strays, ~7%); ~11k self-reference rows — which is exactly what the head commit
  "stop shipping claims the data contradicts" exists to prevent. Since the only real remedy is the
  F57 cleanup, which improves the data whether or not the card exists, keeping the card buys no
  capability while shipping wrong lexicography.
- **Why FIX:** "the data survives in the etymons table, so the card buys nothing" proves the feature
  is *cheap*, not valueless — by that logic every derived lexicographic view is redundant with its
  source rows, and RQ1 is *structuring* a dictionary, not merely possessing etymon rows. The
  false-equivalence problem is the broken≠delete trap: "currently emits wrong output" licenses
  FIX/gate, not deletion, unless wrong-by-design — and the encoding is already correct. F54's own cut
  list omits cognates. So: **FIX** — gate re-ship behind the queued F57 etymon cleanup (post-parse
  assertions: drop self-reference rows, accented/combining-form duplicates, illegal word-final terms,
  chronologically inverted chains) landing first or together, and add the cognate-local calibration
  in the same pass (exclude/deprioritise proto-language anchors `ine-pro`/`grk-pro`; prefer the
  most-specific Greek-stage root). No Tier B, no Leipzig dependency — which is what keeps this a FIX,
  not a DEFER.

### 7 · Domain chips (classifier output) + `lemma_domain_pred`
Word-page chips: `main.py:432` → `WordPage.tsx:66-73` → `labels.ts:416-430`. Classifier:
`lemma_domain_pred`, consumed only by Explore by-field (`main.py:1242-1289`). **Verdict: FIX (L).**

- **Strongest keep:** the deletion item is a **category error**. Item #7 names "domain chips
  (classifier output)," but those chips render *gold* Wiktionary subject-field topics from
  `senses.tags` — verified: **96,275 tagged senses**, ≈23.6k carrying a recognized subject-field
  topic (medicine 4,258, chemistry 1,566, nautical 1,370, all verified live), score=1.0,
  source-attributed, **untouched by every ML audit finding** and unregenerable without re-ingesting
  Wiktionary. That is literally RQ1 dictionary content. The redesign's own page spec even retains
  this rendering (`REDESIGN.md:422`) while contradictorily listing it for deletion (`:451`).
- **Strongest cut:** the *only* genuine classifier surface, `lemma_domain_pred`, has one distinct
  value-add — field-conditioned drift — and that pathway is structurally gated behind the drift table
  (`main.py:1314: if field in doms and lid in drift`), which is 0 rows and audited ~96% noise. Gold
  tags already carry field metadata at score=1.0, so the classifier only duplicates, more noisily,
  data the DB already holds — at an 8–10 h NC-corpus rebuild whose sole consumer is a dead surface.
- **Why FIX:** do not execute the deletion as written — it points the classifier's numbers (0.56
  accuracy, 61% below CONF_FLOOR; and it even cites `main.py:1188`, a trends loop that is not the
  chip renderer) at a working, sourced, RQ1-serving feature those numbers do not describe. Verdicts
  split four ways: **(1)** gold domain metadata → KEEP as-is, effort 0; **(2)** the indigo per-sense
  chip encoding → KEEP; **(3)** the «εμπιστοσύνη N%» number (`ExplorePage.tsx:332`) is genuinely
  wrong (F17/C14: economics 0.55→~0.076 posterior vs medicine ~0.881 at the same displayed %) →
  REPLACE with a coarse band or drop (AUDIT rec #8); **(4)** the classifier proper is broken-but-
  fixable (F16 no reject class: μεγάλος→mathematics 0.666; F17; F18 unreproducible, MIN score 0.30) →
  its stated purpose (densify the ~15k gold-tagged lemmas so field-conditioned drift has coverage) is
  an RQ2 enabler → recalibrate under wave #47, but **DEFER** the rebuild until #47 **plus** a NONE/
  reject class **plus** a corrected (non-noise) drift consumer exist.

### 8 · Mobile tab strip + three viewport-branched JSX trees + `useMediaQuery` gates
`WordPage.tsx:624-625, 781-808, 810-825, 827-837`; `hooks/useMediaQuery.ts`.
**Verdict: REPLACE (M).**

- **Strongest keep:** these three branches are the sole render surface for RQ1 (form→lemma, 541,759
  senses) and RQ3 (bilingual glosses), so "delete" can only mean "re-render" — which the deletion
  PR's own justification column concedes: *"Replaced by one tree with `container-type: inline-size`"*
  (`REDESIGN.md:453`). A straight CUT strands the entire live RQ1/RQ3 delivery layer.
- **Strongest cut:** the fork exists for exactly one reason — mount Cytoscape once so it never sizes
  0×0 in a `display:none` branch (`useMediaQuery.ts:3-6` gating `WordPage.tsx:624-625`). Demote the
  graph (item 3) and the branching, the tab strip and the hook lose their sole function; the RQ1/RQ3
  content reflows in one document flow at every width, so nothing must be built in its place. Keeping
  the mobile «Σχέσεις» tab (a bare canvas with zero accessible content, F34) is strictly worse than
  removing it.
- **Why REPLACE:** this item serves *none* of RQ1/RQ2/RQ3 — it is delivery plumbing owning zero DB
  tables, so the reframe's "broken instrument = recalibrate" protection does **not** attach (that
  protection guards RQ2 methodology, not UI forks). But the word-page capability must survive, so a
  pure CUT is wrong; and a minimal FIX that bolts `aria` roles onto three trees preserves exactly the
  architecture that should go. The construct is genuinely wrong-by-design (WCAG 3.2.3/3.2.4 for the
  three navigations; 1.3.1 for the non-semantic tab strip). Collapse to one `container-type:
  inline-size` tree; route `EntryFamily` into the relations view (never a bare canvas); give the tabs
  real tablist semantics or convert to disclosure zones. **Sequenced with item 3:** if the graph is
  demoted the mount-once constraint vanishes and effort drops to S; if a live canvas is kept a
  mount-once guard keeps it at M. No Tier-B dependency.

### 9 · The ~8 explore/diachronic route handlers in `services/api/app/main.py`
`word_graph:597`, `word_diachronic:945`, `drift_insights:1046`, `explore_overview:1116`,
`explore_interesting:1148`, `explore_by_field:1289`, `explore_trends:1347`, `explore_compare:1462`.
**Verdict: FIX (L).**

- **Strongest keep:** these handlers *are* the code-level operationalization of RQ1/RQ2, not
  accretion. `word_graph` serves live RQ1 data now (relations 294,040, etymons 57,790, verified). The
  other seven carry the RQ2 instrument on literature-tracked estimators the audit itself endorses —
  `_theil_sen_slope:823`, `_mann_kendall_p:841`, Dunning G² `_log_likelihood_g2:871`, Hardie Log
  Ratio `_hardie_log_ratio:887`, Gries DP `_dp:1582`, the rank-percentile cross-corpus comparison
  `:1492`. Every defect maps to a queued fix (#43–#51). Deleting discards the recalibratable
  apparatus mid-fix.
- **Strongest cut:** the research instrument is the *offline* estimator + recalibration pipeline (a
  batch/notebook activity), not a live FastAPI surface reading precomputed tables. The estimators are
  ~200 relocatable LOC, so ~763 LOC of handlers can go without losing capability — and keeping them
  live is a liability: seven read empty tables today, and post-rebuild they re-emit audit-proven
  artefacts under a UI that (F39) misnames the method as OLS+t-test. For a branch whose Phase-0 commit
  is "stop shipping claims the data contradicts," a live «καμπή {year}» from a missing-year hole is
  the posture violation to avoid.
- **Why FIX:** the cut is right about *posture* and wrong about *deletion*. Its premise — that the
  handlers are a thin veneer over relocatable helpers — is false: the composition logic the waves
  recalibrate (which candidates to test, in what order, which FDR correction, which CI bound to rank
  on) lives *inside* `explore_trends`/`explore_interesting`/`explore_compare`, not in the helpers.
  Deleting them throws away exactly the operationalization the waves edit, forcing a later rewrite —
  churn on active, specified work. The Phase-0 risk is real but avoidable by **sequencing, not
  deletion**: the tables are empty now (handlers emit nothing today), so the only exposure window is
  post-rebuild, precisely when the fixes are scheduled. Keep `word_graph` live now (its node-link
  *visual* is the separate item-3 REPLACE); keep and recalibrate the seven in place; relabel per F39;
  **gate live exposure** of non-empty payloads behind the corrected Tier B rebuild.

---

## 4. What genuinely should still be cut or replaced

The reframe rescues the *studies*; it does not rescue two wrong-by-design encodings or a set of false
labels. Honest list of what actually dies:

1. **The Cytoscape node-link canvas + `cytoscape` + `@types/cytoscape` (438,616 B).** Wrong encoding
   for a median-degree-2, 86.2%-empty relation set (F34), framing-independent. Replaced by typed text
   lists that already exist and are strictly better on links, provenance, and a11y. **The endpoint
   and tables stay.**
2. **The three viewport-branched JSX trees + `useMediaQuery` gates + the non-semantic mobile tab
   strip.** WCAG 3.2.3/3.2.4/1.3.1 defects (F34). Replaced by one container-query tree. The word-page
   capability stays.
3. **Four false / overclaiming UI labels — suppress regardless of framing** (they are the branch's
   own Phase-0 mission): the hard «καμπή ~{year}» over a NULL change-point score
   (`DiachronicPanel.tsx:228-236`); the σημαντική chip with no null (`:211-226`); the uncalibrated
   «εμπιστοσύνη N%» (`ExplorePage.tsx:332`); the «ομοιότητα X%» meaning-identity framing on
   `EntryNeighbors`.
4. **The `EntryNeighbors` consumer card + the `neighbors` API field** — drop or relabel to
   distributional; keep the table as the internal diagnostic the redesign already proposed.
5. **The Explore by-field sub-panel** — drop until classifier #47 lands.
6. **The `/movers` redirect** — trivially removable once Explore's routing is revisited (cosmetic).

Everything else the PR listed is a data layer to keep-and-recalibrate, a correct rendering to keep,
or a card to demote — **not** a deletion.

---

## 5. The revised plan (replaces "Phase 1: the deletion PR")

The original Phase 1 was "delete −1,158 LOC front-end, −763 LOC back-end, −438,616 B JS, order-
independent, no data dependency." It is replaced by a **Phase 1′** that ships the two genuine
encoding cuts and the honesty gates now, keeps every data layer, and sequences repopulation behind
the methodology waves so no miscalibrated number is ever served.

### Phase 1′ — Encoding cuts + honesty gates · ~4–5 d · no data dependency, order-independent
Ships alone, before anything is added. Everything here is framing-independent and needs no rebuild.

- **REPLACE the relations rendering** (item 3): delete `RelationGraph.tsx` + `cytoscape` +
  `@types/cytoscape`; promote `SynonymBlock`/`WordFamily`/`EntryFamily` to the primary relations UI;
  etymology as an ordered lineage path. **KEEP** `GET /api/word/{lemma}/graph` and the relations/
  etymons tables.
- **REPLACE the responsive shell** (item 8): collapse the three viewport trees to one
  `container-type: inline-size` tree; route `EntryFamily` into the relations view; real tablist
  semantics or disclosure zones. Sequence *after/with* the graph replacement (they are coupled).
- **Honesty gates (Phase-0 overlap)**: suppress «καμπή ~{year}» while `change_point_score IS NULL`
  (`main.py:957`); hide the σημαντική chip until F8's null; replace «εμπιστοσύνη N%» with a band or
  drop it; relabel/demote `EntryNeighbors`. Add honest "pending recalibration" empty states and fix
  the `setData(null)` error-swallow (`ExplorePage.tsx:353`).
- **KEEP as-is, no action** (correct + live now): word-page gold domain chips; `EntryCognates`;
  `word_graph` endpoint data.
- **DEFER, no action** (item 4): leave `EntryDescendants` code + `--descendants-only` pass + no-op
  card in place; do not repopulate.

Net vs the original PR: it still drops the 438 kB dependency and the a11y-broken forks, but it
deletes **zero** data layers and **zero** endpoints.

### Then, the data/method work — sequenced against the queued waves
This is where the reframe's real cost lives, and it is genuine research, not maintenance.

1. **Land the methodology waves offline first** (BACKLOG #43–#51), validated in a permutation-null /
   bootstrap harness *before* any panel is repopulated: #45 trends (F10/F39), #46 keyness (F20/F43),
   #43 bootstrap K≥100 BCa, #44 change-point PELT/CUSUM with a null, #48 anchored Procrustes, #49
   pooling, #50 seeded reruns (`workers=1`), #47 classifier calibration + abstain + NONE class.
2. **Corrected Tier B rebuild** (`_reingest_methodology_waves.sh`, ≈8–10 h). Reintroduces the CC
   BY-NC Leipzig data + word2vec + bootstrap. The maintainer has scoped licensing as a non-blocker
   for a non-distributed research project — see Open Decision B.
3. **Repopulate per-panel, gated behind each wave** (using `explore_cache`, `main.py:146`): light up
   trends only after #45, keyness only after #46, drift-movers only after #43/#48/#50 **and** the D3
   go/no-go, DiachronicPanel only after its gates + rebuild. **by-field stays dark** until #47.
   `EntryNeighbors`/`semantic_neighbors` regenerate on the same word2vec pass with the F37
   `pos!='name'` filter + seed/workers=1.
4. **`EntryCognates` cleanup** — independent of Tier B (Tier A self-join): gate re-ship behind the
   F57 etymon post-parse assertions + cognate-local ranking/dedup.
5. **Classifier rebuild** (`lemma_domain_pred`) — only after #47 + NONE class + a corrected drift
   consumer.

### Interaction with the redesign's other phases
- **Phase 0** ("stop shipping falsehoods", 4 d) — mostly absorbed by the Phase 1′ honesty gates; the
  licensing/attribution items (0.9, 0.10) remain and now interlock with Open Decision B.
- **Phase 2** (names, sources, provenance, 8 d) and **Phase 3** (search cascade + eval harness,
  13 d) are **unaffected** by this record and proceed as written — they were never in tension with
  the deletion PR.

### Genuine deletion / fix / re-render / deferred — the one-line ledger
- **Genuine deletion:** the Cytoscape canvas + `cytoscape` dep; the three viewport-branched trees +
  `useMediaQuery` gates + non-semantic tab strip; four false UI labels; the `EntryNeighbors` card +
  `neighbors` field; the by-field panel (until #47); `/movers`.
- **Fix (recalibrate in place):** ExplorePage methods, DiachronicPanel methods, the seven diachronic
  handlers, `semantic_neighbors`, `EntryCognates`/F57, the classifier.
- **Re-render:** relations (list, not graph); the responsive word page (one container-query tree);
  demoted relation cards.
- **Deferred:** `EntryDescendants` (table + pass + card); the classifier rebuild; drift-movers
  population (behind D3).

---

## 6. Open decisions for the maintainer

**A · D3 — is drift/change-point worth the 8–10 h Tier B rebuild?** *(the single most consequential
call)* The estimators can be recalibrated (waves #43/#44/#48/#50), but F38 flags a corpus-power
ceiling: Parliament + news are both formal *written* Greek, with a 3-year hole and a 3.3× size jump
at 2019. The honest options (BACKLOG D3) are **fix / demote-to-exploratory-with-warnings / remove**.
*Tradeoff:* fixing buys RQ2's word-level altitude but may still yield a low-power signal; demoting
ships the panels labelled exploratory; removing forfeits the study. Recommendation: recalibrate
offline, then decide fix-vs-demote on the *post-recalibration* signal, not the current noise.

**B · Licensing / redistribution (D6) for the rebuild.** Tier B reintroduces CC BY-NC Leipzig +
276,769 verbatim news sentences. You have scoped licensing as a non-blocker for a *non-distributed*
research DB. *Confirm:* the DB stays non-distributed, and no public snapshot / OntoLex export ships
the NC corpus text or derived counts under a CC BY-SA claim (this gates `REDESIGN.md` Phase-0 item
0.10 and every "open data" claim). *Tradeoff:* the moment a snapshot is published, the reframe's
licensing exemption lapses and B blocks it.

**C · Is contact-linguistics / forward-etymology an actual research question (candidate RQ4)?** If
yes, `EntryDescendants` leaves DEFER and gets the cheap repopulation pass (minutes, no Tier B, no new
licensing); the 610/849 Balkan-sprachbund items become a first-class object. If no, it stays
deferred. *Tradeoff:* near-zero cost to re-enable vs. one more surface to maintain for a question you
have not posed.

**D · Should RQ2 be served by a live SPA at all, or by an offline harness feeding a read-only
viewer?** The strongest cut argument's real force: the *validated* estimator is an offline artefact,
and a live interactive Explore surface whose API contract every wave churns may be premature.
*Tradeoff:* keep ExplorePage/DiachronicPanel as the interactive RQ2 surface (this record's default,
gated per-wave) vs. run the estimators in a notebook and let the web pages render only frozen,
validated outputs — cheaper to keep honest, but loses interactive exploration.

**E · by-field Explore panel — revive after #47, or drop permanently?** It compounds an unevaluated
classifier with an unevaluated trend. *Tradeoff:* revive only if field-conditioned drift proves a
distinct research need after #47 + a corrected drift consumer both land; otherwise it is the one
Explore sub-panel with no independent justification.
