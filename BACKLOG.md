# BACKLOG — Λεξόραμα

**Single source of truth.** Every bug, critical issue, fix, new feature, and open
discussion point lives here. Do not create new dated or ad-hoc `.md` files for findings —
add an item to this file instead.

- **Evidence base:** [`docs/AUDIT.md`](docs/AUDIT.md) — the 2026-07-21 adversarial
  methodology audit (143 agents, 63 verified findings, 8 literature reviews, 148
  references). Item IDs `F1`–`F63` are that report's finding IDs and are stable.
- **Legacy IDs** `#28`–`#51` come from the previous `docs/backlog.md`, now folded in and
  deleted. IDs are never reused.
- **Shipped work** is recorded in [`HANDOFF.md`](HANDOFF.md) under "Done".

## Status legend

| Mark | Meaning |
|---|---|
| `[ ]` | open |
| `[~]` | in progress |
| `[x]` | done — flip with a date, move the detail to `HANDOFF.md` |
| `[?]` | needs a maintainer decision (see § Discussion points) |

The **verified** note on each item (`2/2`, `1/2`, `critic`) records how many independent
adversarial verifiers confirmed it. `1/2` means one verifier pushed back on severity or
scope — read the linked audit section before acting.

---

## Now — active remediation

Sequenced deliberately: make divergence **detectable** first, then stop the **data loss**,
then stop the **false claims**.

- [x] **R1 — Build manifest + schema version.** *(2026-07-21)*
  `pipelines/ingest/manifest.py`: `schema_meta` version stamp + `build_manifest`
  (component, git commit + dirty flag, input fingerprints, params, row counts), recorded
  by `ingest_kaikki` and `build_search_index`. Paired with **data-evidence checks** that
  detect divergence on a DB with no manifest at all — which is how the audit caught this.
  Surfaced at `GET /api/health` (`build.diverged`) and `GET /api/build-status`; CLI
  `python pipelines/ingest/manifest.py --db …` exits 1 on failure, ready to gate CI (#42).
  12 tests. **Against the live DB: 0/6 checks pass**, reproducing F2/F5/F9/F18/F21/F60
  independently.
- [x] **R2 — Accent-folding lemma key fixed.** *(2026-07-21)*
  Lemma identity is now `(lemma, pos)` — the accented surface; `normalized_lemma` stays
  the *search* key, so homographs remain reachable by the shared folded key and are
  disambiguated at ranking, as invariant #2 always intended. `find_lemma_id()` resolves
  the `--*-only` passes by exact surface and **returns None rather than guess** between
  homographs. `SCHEMA_VERSION` → 2; 16 tests in `tests/test_homographs.py`.
  ⚠ **The existing 1.5 GB DB still carries the loss** — merged rows are gone and only a
  full re-ingest under v2 recovers them (see R2-followup).
- [x] **R3 — User-facing claims gated on real data.** *(2026-07-21)*
  ExplorePage copy corrected to the estimator the code actually runs (Theil–Sen slope,
  Mann–Kendall test, BH-FDR — it was claiming least-squares + t-test, F39).
  MethodologyPage now renders a `DataStatusBanner` driven by `/api/build-status`: it names,
  in Greek, exactly which documented methods the *currently served* data does not reflect.
  Chosen over rewriting the prose because a hard-coded disclaimer would itself become a
  lie after a re-ingest — the banner disappears automatically when the checks pass.
  Verified in-browser; `tsc` and `npm run build` clean.

### Follow-ups opened by the remediation

- [x] **N1 — RETRACTED, not a defect.** *(raised and withdrawn 2026-07-21)*
  I reported that the Κλίση panel did not render at desktop width. It does. The desktop
  branch renders `formsDisclosure` (`WordPage.tsx:714-753`), a progressive disclosure that
  is **collapsed by default by design** — the code comment says so — and mounts its tables
  only on click (`{formsOpen && …}`). Confirmed at 1280×900: 0 tables before the click,
  **4 tables after**, both voice grids, `aria-expanded` → `true`.
  Two probe errors caused the false positive, both mine: I read "no mounted `<table>`" as
  "not rendered" on a deliberately collapsed panel, then my follow-up finder matched
  `includes('Κλίση')` against a label that Tailwind's `uppercase` renders as **ΚΛΙΣΗ**, so
  `innerText` never matched and I concluded the button was absent too.
  *Lesson worth keeping: when probing a UI, assert on the accessibility tree or on
  `aria-expanded`, not on the presence of descendants that progressive disclosure is
  supposed to withhold — and never case-match text that CSS may have transformed.*

- [ ] **R2-followup — Re-ingest under schema_version 2 to recover the lost words.** The
  key is fixed but the shipped DB predates it. Requires a full `ingest_kaikki` re-run
  (el then en) + `build_search_index`, with the API stopped. Large operation, maintainer's
  call. Until then `/api/build-status` reports `lemma_identity` as failing and the
  methodology banner stays up.
- [ ] **R1-followup — Record builds from the remaining pipelines.** `record_build()` is
  wired into `ingest_kaikki` and `build_search_index` only. Add it to `classify_domains`,
  `ingest_diachronic`, `bootstrap_drift`, `ingest_frequency`, `ingest_collocations`,
  `build_gloss_index` so `manifest_coverage` can actually pass. *Effort: S.*
- [ ] **R1-followup — Wire the checker into CI** as a gate once #42 exists; it already
  exits non-zero.

---

## Critical

These invalidate user-visible numbers or destroy data. Nothing claiming methodological
rigor should ship before they are closed.

- [ ] **F1** `critical` — Greek guillemets `«»` indexed as forms of περιπλέκω → rank 4 of user-facing news keyness, G²=4.76M  
  <sub>Lexicographic · verified 2/2 · [evidence](docs/AUDIT.md#34-lexicographic--corpus-linguistic-method)</sub>
- [ ] **F2** `critical` — Per-lemma frequency sums to 1,026% of corpus; 33.6% is duplicate-row double-add; MAX(zipf)=8.615  
  <sub>Lexicographic · verified 2/2 · [evidence](docs/AUDIT.md#34-lexicographic--corpus-linguistic-method)</sub>
- [ ] **F3** `critical` — 99% of el-wiktionary verb forms lack a voice tag → 115,326 cells merge active + mediopassive  
  <sub>Greek correctness · verified critic · [evidence](docs/AUDIT.md#36-modern-greek-linguistic-correctness)</sub>
- [ ] **F4** `critical` — Bare endings (`ο`,`ος`,`ων`) stored as forms; αισώπειος = 0.81% of parliament, #1 falling word  
  <sub>Completeness · verified critic · [evidence](docs/AUDIT.md#312-completeness-pass--subsystems-the-main-audit-never-examined)</sub>
- [ ] **F5** `critical` — `change_point_year` is a corpus-gap artifact (82.6% of news = 2016); advertised z≥2 gate never applied  
  <sub>Diachronic · verified 2/2 · [evidence](docs/AUDIT.md#32-diachronic-embedding-methodology)</sub>
- [ ] **F6** `critical` — No CI, no integration tests; 13 route handlers and 2,016 LOC of pipeline untested; tests ratify the homograph merge  
  <sub>Software eng · verified 1/2 · [evidence](docs/AUDIT.md#311-software-engineering-correctness--operations)</sub>

---

## By subsystem

All remaining findings, grouped by where the fix lands. Severity-ordered within each group.

### Corpus attribution, frequency & collocations
<sub>2 high · 1 medium</sub>

- [ ] **F19** `high` — Collocations are sentence co-occurrence labelled «Τυπικές συνάψεις»; window file `co_n` unused  
  <sub>Lexicographic · verified 2/2 · [evidence](docs/AUDIT.md#34-lexicographic--corpus-linguistic-method)</sub>
- [ ] **F20** `high` — Gries DP gate rejects 0.40% of candidates; G² on ~5.5x-inflated counts; no multiple-testing correction  
  <sub>Lexicographic · verified 1/2 · [evidence](docs/AUDIT.md#34-lexicographic--corpus-linguistic-method)</sub>
- [ ] **F48** `medium` — Example selection has no GDEX target-sensitive criterion; 24.0% of lemmas are tie-frozen arrival order  
  <sub>Lexicographic · verified 2/2 · [evidence](docs/AUDIT.md#34-lexicographic--corpus-linguistic-method)</sub>

### Greek linguistic correctness
<sub>3 high · 2 medium</sub>

- [ ] **F40** `high` — `greek_accent` blind to polytonic and capital accents → 171 double-accented generated forms, all indexed  
  <sub>Greek correctness · verified critic · [evidence](docs/AUDIT.md#36-modern-greek-linguistic-correctness)</sub>
- [ ] **F41** `high` — Greeklish table has no `v`→β; greedy digraph scan; 12 of 24 ordinary spellings fail  
  <sub>Greek correctness · verified critic · [evidence](docs/AUDIT.md#36-modern-greek-linguistic-correctness)</sub>
- [ ] **F42** `high` — Gender-NULL nouns get the masculine -ος paradigm (`καταστρώματε`, `θελήματοι`)  
  <sub>Greek correctness · verified critic · [evidence](docs/AUDIT.md#36-modern-greek-linguistic-correctness)</sub>
- [ ] **F58** `medium` — Definite articles ingested as forms (300 rows); Katharevousa dative rendered in the demotic 4-case grid  
  <sub>Greek correctness · verified critic · [evidence](docs/AUDIT.md#36-modern-greek-linguistic-correctness)</sub>
- [ ] **F59** `medium` — ≥0.97 gate scored only where Wiktionary has a form; backfill writes only where it doesn't  
  <sub>Greek correctness · verified critic · [evidence](docs/AUDIT.md#36-modern-greek-linguistic-correctness)</sub>

### Diachronic semantics
<sub>4 high · 1 medium</sub>

- [ ] **F12** `high` — Drift trajectories are step functions; 96.4% of news drift present at slice 3  
  <sub>Diachronic · verified 1/2 · [evidence](docs/AUDIT.md#32-diachronic-embedding-methodology)</sub>
- [ ] **F13** `high` — Frequency confound uncontrolled (ρ=−0.547); both "frequency-robust" measures equally confounded  
  <sub>Diachronic · verified 1/2 · [evidence](docs/AUDIT.md#32-diachronic-embedding-methodology)</sub>
- [ ] **F14** `high` — Procrustes not Hamilton-compliant; anchor pruning selects on vector norm (corr 0.996), not drift  
  <sub>Diachronic · verified 1/2 · [evidence](docs/AUDIT.md#32-diachronic-embedding-methodology)</sub>
- [ ] **F15** `high` — ±2-year pooling weighted by raw line count; slice labelled 2018 is 69% 2019–2020 text  
  <sub>Diachronic · verified 2/2 · [evidence](docs/AUDIT.md#32-diachronic-embedding-methodology)</sub>
- [ ] **F44** `medium` — No diachronic result is reproducible: word2vec trained with `workers=cpu_count()`, no seed  
  <sub>Diachronic · verified 1/2 · [evidence](docs/AUDIT.md#32-diachronic-embedding-methodology)</sub>

### Statistical inference
<sub>5 high · 1 medium</sub>

- [ ] **F7** `high` — Reported drift is ~96% saturating estimator noise; the control cannot see it  
  <sub>Statistics · verified 1/2 · [evidence](docs/AUDIT.md#31-statistical-inference-validity)</sub>
- [ ] **F8** `high` — `drift_significant`/`drift_q` divide by a replicate SD, not a standard error — not a test  
  <sub>Statistics · verified 2/2 · [evidence](docs/AUDIT.md#31-statistical-inference-validity)</sub>
- [ ] **F9** `high` — All 20,255 change points shipped ungated; `change_point_score` NULL in 100% of rows  
  <sub>Statistics · verified 2/2 · [evidence](docs/AUDIT.md#31-statistical-inference-validity)</sub>
- [ ] **F10** `high` — `explore_trends` selects on R² then tests the same data; global-null FDR = 100% at n=31  
  <sub>Statistics · verified 2/2 · [evidence](docs/AUDIT.md#31-statistical-inference-validity)</sub>
- [ ] **F11** `high` — K=12 percentile CI has 82.0% coverage; 430/1,266 point estimates fall outside their own CI  
  <sub>Statistics · verified 2/2 · [evidence](docs/AUDIT.md#31-statistical-inference-validity)</sub>
- [ ] **F43** `medium` — Keyness gate passes 88.4% of candidates; displayed top-30 has 10x the CI width of the pool  
  <sub>Statistics · verified 1/2 · [evidence](docs/AUDIT.md#31-statistical-inference-validity)</sub>

### Classifier / ML evaluation
<sub>3 high · 3 medium</sub>

- [ ] **F16** `high` — No reject class: evaluated on words that have a field, deployed on 93,563 that mostly don't (μεγάλος→mathematics 0.666)  
  <sub>ML eval · verified 1/2 · [evidence](docs/AUDIT.md#33-ml--classifier-evaluation-rigor)</sub>
- [ ] **F17** `high` — `class_weight='balanced'` + one absolute gate: 0.55 = posterior 0.076 (economics) vs 0.881 (medicine)  
  <sub>ML eval · verified 1/2 · [evidence](docs/AUDIT.md#33-ml--classifier-evaluation-rigor)</sub>
- [ ] **F18** `high` — Shipped `lemma_domain_pred` not produced by repo code; 61% below current CONF_FLOOR; unreproducible  
  <sub>ML eval · verified 1/2 · [evidence](docs/AUDIT.md#33-ml--classifier-evaluation-rigor)</sub>
- [ ] **F45** `medium` — Reported metrics describe a different model under a different decision rule than the one that shipped  
  <sub>ML eval · verified 1/2 · [evidence](docs/AUDIT.md#33-ml--classifier-evaluation-rigor)</sub>
- [ ] **F46** `medium` — Single 20% split at seed 0, no CV, no CI, ~4 test examples in the smallest class — and it chose the architecture  
  <sub>ML eval · verified 1/2 · [evidence](docs/AUDIT.md#33-ml--classifier-evaluation-rigor)</sub>
- [ ] **F47** `medium` — No threshold tuned on data; the ≥0.97 paradigm gate exists only in docstrings; 0 of 87 tests touch ML  
  <sub>ML eval · verified 1/2 · [evidence](docs/AUDIT.md#33-ml--classifier-evaluation-rigor)</sub>

### Morphology & normalization
<sub>3 high · 1 medium · 1 low</sub>

- [ ] **F21** `high` — Accent-folding lemma key permanently deleted headwords (ποτέ, νομός, δουλεία, χαλί, κάλος = 0 rows)  
  <sub>Morphology · verified 1/2 · [evidence](docs/AUDIT.md#35-morphology--paradigm-engine)</sub>
- [ ] **F22** `high` — -ους accusative plural takes the same lexical accent shift as the dropped genitive: 0.868, hidden by class averaging  
  <sub>Morphology · verified 1/2 · [evidence](docs/AUDIT.md#35-morphology--paradigm-engine)</sub>
- [ ] **F23** `high` — Greeklish fan-out unmeasured; greedy `nt` makes every νθ word unreachable (`anthropos`→`αντηροποσ`)  
  <sub>Morphology · verified 1/2 · [evidence](docs/AUDIT.md#35-morphology--paradigm-engine)</sub>
- [ ] **F49** `medium` — The ≥0.97 gate is measured on exactly the cells that are never shipped (disjoint by construction)  
  <sub>Morphology · verified 1/2 · [evidence](docs/AUDIT.md#35-morphology--paradigm-engine)</sub>
- [ ] **F62** `low` — `greek_accent.py:20` claims "Validated in tests"; zero tests exist; `_class_of` mis-buckets every oxytone noun  
  <sub>Morphology · verified 1/2 · [evidence](docs/AUDIT.md#35-morphology--paradigm-engine)</sub>

### Provenance, licensing & reproducibility
<sub>3 high · 1 medium · 2 low</sub>

- [ ] **F24** `high` — `record_attribution` fails open: 4 corpora / 2.53M rows with no license, incl. the default Explore axis  
  <sub>Provenance · verified 2/2 · [evidence](docs/AUDIT.md#37-data-model-provenance--licensing-integrity)</sub>
- [ ] **F25** `high` — 276,769 verbatim news sentences redistributed; the per-sentence publisher file `-sources.txt` never read  
  <sub>Provenance · verified 2/2 · [evidence](docs/AUDIT.md#37-data-model-provenance--licensing-integrity)</sub>
- [ ] **F26** `high` — `search_index` has no `source` column: 155,604 generated forms served as attested  
  <sub>Provenance · verified 1/2 · [evidence](docs/AUDIT.md#37-data-model-provenance--licensing-integrity)</sub>
- [ ] **F50** `medium` — `--sense-tags-only` UPDATE key is non-unique over 36,179 sense rows; corrupts classifier gold  
  <sub>Provenance · verified 1/2 · [evidence](docs/AUDIT.md#37-data-model-provenance--licensing-integrity)</sub>
- [ ] **F60** `low` — `ingest_diachronic` truncates `bootstrap_drift`'s output; 91% of shipped CIs gone, unreproducible  
  <sub>Provenance · verified 1/2 · [evidence](docs/AUDIT.md#37-data-model-provenance--licensing-integrity)</sub>
- [ ] **F61** `low` — Derived-DB obligations asserted in prose only: no LICENSE file, no snapshot, WordNet 3.0 notice absent  
  <sub>Provenance · verified 1/2 · [evidence](docs/AUDIT.md#37-data-model-provenance--licensing-integrity)</sub>

### Search & retrieval
<sub>4 high · 1 medium</sub>

- [ ] **F27** `high` — Zero IR evaluation anywhere in the repo; flagship feature validated by two anecdotes on a 3-lemma fixture  
  <sub>Search · verified 1/2 · [evidence](docs/AUDIT.md#38-search--retrieval-quality--evaluation)</sub>
- [ ] **F28** `high` — Greeklish resolver has no `v`→β, maps `x`→ξ only; 16.3% zero-result on the visual convention  
  <sub>Search · verified 2/2 · [evidence](docs/AUDIT.md#38-search--retrieval-quality--evaluation)</sub>
- [ ] **F29** `high` — No prefix/fuzzy/typo matching: 68.2% of as-you-type prefixes and 97.9% of 1-char typos return nothing  
  <sub>Search · verified 2/2 · [evidence](docs/AUDIT.md#38-search--retrieval-quality--evaluation)</sub>
- [ ] **F30** `high` — en→el gloss index ranks by Greek corpus frequency ('book'→κλείνω before βιβλίο); API key ≠ indexed key  
  <sub>Search · verified 2/2 · [evidence](docs/AUDIT.md#38-search--retrieval-quality--evaluation)</sub>
- [ ] **F51** `medium` — Lemma-level dedupe silently discards 1,223,148 of 1,805,293 grammatical analyses  
  <sub>Search · verified 1/2 · [evidence](docs/AUDIT.md#38-search--retrieval-quality--evaluation)</sub>

### Product & concept
<sub>4 high · 2 medium</sub>

- [ ] **F32** `high` — Feature (a): 30.9% of form/lemma pairs are ambiguous; one analysis shown, chosen by physical row order  
  <sub>Product · verified 1/2 · [evidence](docs/AUDIT.md#310-conceptual--product-architecture)</sub>
- [ ] **F33** `high` — Feature (b): 62.6% of rendered edges are the untyped `related` AboutPage promises to exclude; edge source never rendered  
  <sub>Product · verified 2/2 · [evidence](docs/AUDIT.md#310-conceptual--product-architecture)</sub>
- [ ] **F34** `high` — The graph is a median-3-edge star; mobile Σχέσεις tab has zero accessible content  
  <sub>Product · verified 2/2 · [evidence](docs/AUDIT.md#310-conceptual--product-architecture)</sub>
- [ ] **F35** `high` — MethodologyPage states three methods as present fact that the shipped DB was not produced with  
  <sub>Product · verified 2/2 · [evidence](docs/AUDIT.md#310-conceptual--product-architecture)</sub>
- [ ] **F53** `medium` — WordNet is-a edges are lemma-level projections of an English sense partition, no sense anchor  
  <sub>Product · verified 2/2 · [evidence](docs/AUDIT.md#310-conceptual--product-architecture)</sub>
- [ ] **F54** `medium` — Feature accretion: 14 word-page surfaces, 20 pipelines, 2 measured quality numbers, one card for 0.4% coverage  
  <sub>Product · verified 1/2 · [evidence](docs/AUDIT.md#310-conceptual--product-architecture)</sub>

### Engineering & operations
<sub>1 high · 1 medium · 1 low</sub>

- [ ] **F36** `high` — `/api/word` fan-out unbounded: one GET returns 1,377 entries ≈ 46 MB  
  <sub>Software eng · verified 1/2 · [evidence](docs/AUDIT.md#311-software-engineering-correctness--operations)</sub>
- [ ] **F55** `medium` — Zero input validation: 1 `Query()` constraint in 1,580 lines; user floats become permanent cache rows at 35 s each  
  <sub>Software eng · verified 1/2 · [evidence](docs/AUDIT.md#311-software-engineering-correctness--operations)</sub>
- [ ] **F63** `low` — Two competing schema authorities (`schema.sql` vs inline DDL in `main.py`), no version stamp, duplicated stats code  
  <sub>Software eng · verified 1/2 · [evidence](docs/AUDIT.md#311-software-engineering-correctness--operations)</sub>

### LLM engineering
<sub>1 high · 1 medium</sub>

- [ ] **F31** `high` — Classifier honesty number measured off the deployed distribution; two unlinked gates, no regression test  
  <sub>LLM eng · verified 1/2 · [evidence](docs/AUDIT.md#39-llm-engineering)</sub>
- [ ] **F52** `medium` — No grounding substrate: 58% of content lemmas have zero corpus examples, 47% of senses have <20-char glosses  
  <sub>LLM eng · verified 1/2 · [evidence](docs/AUDIT.md#39-llm-engineering)</sub>

### Cross-cutting (completeness pass)
<sub>3 high · 2 medium</sub>

- [ ] **F37** `high` — 75.4% of lemmas are proper names; surname homographs of function words hold top-100 Zipf ranks  
  <sub>Completeness · verified critic · [evidence](docs/AUDIT.md#312-completeness-pass--subsystems-the-main-audit-never-examined)</sub>
- [ ] **F38** `high` — Both corpora are one formal written register; parliament's #2 rising word is a chamber-address artifact (κυρία)  
  <sub>Completeness · verified critic · [evidence](docs/AUDIT.md#312-completeness-pass--subsystems-the-main-audit-never-examined)</sub>
- [ ] **F39** `high` — ExplorePage tells users OLS + t-test; the code runs Theil–Sen + Mann–Kendall + BH-FDR; cache sig can't see content change  
  <sub>Completeness · verified critic · [evidence](docs/AUDIT.md#312-completeness-pass--subsystems-the-main-audit-never-examined)</sub>
- [ ] **F56** `medium` — Search cards strip register labels and always show sense 0 ('any muslim person'→Τούρκος, unlabelled)  
  <sub>Completeness · verified critic · [evidence](docs/AUDIT.md#312-completeness-pass--subsystems-the-main-audit-never-examined)</sub>
- [ ] **F57** `medium` — Etymology never audited: 10,926 etymons are the lemma itself, 566 self-loops, 297 bare stems  
  <sub>Completeness · verified critic · [evidence](docs/AUDIT.md#312-completeness-pass--subsystems-the-main-audit-never-examined)</sub>

---

## Feature backlog

Carried over from `docs/backlog.md` (now folded in). These are *wanted*, not defects.

- [ ] **#40 — More corpora on their own axes.** Pipeline shipped; blocked purely on data
  acquisition. `--leipzig-source` scopes Layers B/C to one corpus, the axis label derives
  from the folder prefix, and the UI surfaces new axes automatically. What remains:
  download and ingest a second Leipzig corpus (wiki/web) or a literary corpus — large
  dumps, must be pulled **outside** an LLM session (see `pipelines/download_data.ps1`).
  *Effort: L per corpus.*
  <sub>See also F38 — both current corpora are one formal written register, which makes a
  second register a *correctness* concern, not just coverage.</sub>
- [ ] **#41 — Postgres + pg_trgm migration.** SQLite WAL forces the API to stop during
  ingest. Production fuzzy/trigram search and concurrent writes want Postgres.
  *Effort: L.* **(infra — last)**
  <sub>See F29: no prefix/fuzzy/typo matching exists at all today; pg_trgm is the intended
  vehicle, so this is closer to a feature gap than pure infra.</sub>
- [ ] **#42 — CI + automated locked ingest refresh + observability.** Ingest and Layer B/C
  re-runs are manual and the API must be stopped first. No dashboards or alerting on
  unresolved-miss rate. *Effort: M.* **(infra — last)**
  <sub>F6 makes CI urgent rather than "last": nothing currently enforces the 87 tests or
  the ≥0.97 paradigm gate.</sub>

### Methodology waves #43–#51 — reconcile against the audit

**Approach (post-D3):** the corrected estimators are landed OFFLINE as pure, tested
functions in [`pipelines/analysis/estimators.py`](pipelines/analysis/estimators.py) and
validated against a null in the harness FIRST; wiring them into `ingest_diachronic` /
`main.py` and repopulating is a later step, gated behind the Tier B rebuild (D3). This is
why "landed (offline)" below does not yet change any served number — the shipped DB still
has `change_point_score`/`drift_score_boot` NULL until the rebuild runs the new code.

- [x] **#43 — BCa interval landed (offline).** `estimators.bca_interval` (bias-correction
  + acceleration, Efron 1987); coverage unit-tested at ≥0.88 vs the K=12 percentile's ~0.82
  (F11). **Remaining:** wire into `bootstrap_drift.py` and run at K≥100 (the expensive Tier
  B step) — the interval maths is done, the resampling volume is not.
- [x] **#44 — change-point landed + null-validated (offline).** `estimators.change_point`
  (Pettitt 1979 + optional permutation null) replaces the argmax+robust-z heuristic (F5/F9).
  `pipelines/analysis/validate_change_point.py` on a real news no-change trajectory:
  **[A]** flat noise FP 0.0% (new) vs 0.2% (old); **[B]** with one gap-sized spike injected,
  **new 0.0% vs old 100.0%** — reproducing and fixing the "82.6% collapse to the 2016 gap
  year" failure. **Remaining:** wire into `ingest_diachronic.change_point_year`.
- [x] **#45 — autocorrelation-robust trend landed (offline).** `estimators.mann_kendall`
  adds the Hamed & Rao (1998) correction (var(S) inflated by the effective-sample-size
  factor, with the significance filter) so p is honest on serially-correlated annual series
  (F10/F39); unit-tested that it is ≥ the naive p under positive autocorrelation and ≈naive
  for iid. **Remaining:** swap `main.py:_mann_kendall_p` for it; separate the R²-selection
  from the significance test (F10 circularity).
- [x] **#46 — keyness CI + FDR landed (offline).** `estimators` exposes `dunning_g2`,
  `g2_p_value`, `hardie_log_ratio` (with CI) and `bh_fdr`; unit-tested. **Remaining:** apply
  `bh_fdr` across the simultaneous keyness tests in `explore_compare` and report q, not a
  raw p<0.001 claim (F20/F43).
- [x] **#47 — classifier calibration landed + WIRED.** (F16/F17/F45)
  [`calibration.py`](pipelines/analysis/calibration.py): per-class isotonic calibration,
  ECE/Brier/reliability diagnostics, per-class abstain thresholds tuned to a precision
  target, and a precision+coverage report computed under the *deployed* rule (so the
  reported number is the shipped one, F45). Unit-tested (10): isotonic cuts ECE
  **0.157→0.057** on over-confident scores; per-class thresholds hit a precision target
  where a single gate cannot; precision/coverage trade-off holds. **Wired into
  `classify_domains.py`**: CalibratedClassifierCV(isotonic) replaces raw softmax,
  per-class thresholds replace the meaningless absolute `CONF_FLOOR=0.50` (F17), the
  report now describes the deployed calibrated+abstain rule, and it falls back to the raw
  model if a thin field breaks the CV folds (never crashes the rebuild). Runs at the Tier
  B rebuild — the empirical per-field numbers land then.
- [x] **#48 — Hamilton-compliant alignment landed (offline).**
  [`embedding_ops.procrustes_align`](pipelines/analysis/embedding_ops.py) L2-normalizes
  before Procrustes and prunes anchors by a SCALE-FREE cosine residual, not the Euclidean
  `‖A·R−B‖` that scales with norm (F14). Reproduced the audit sim: corr(residual, norm)
  **0.991 → 0.019** (shipped Euclidean → fixed cosine), so pruning drops drifted anchors,
  not high-frequency ones. Unit-tested (rotation recovery, norm-invariance, kept-anchor
  norm distribution). **Remaining:** wire into `ingest_diachronic._align`; also switch
  `_train` `sg=0`→`sg=1` (Hamilton uses SGNS; the classifier already does — F14 aside).
- [x] **#49 — balanced pooling landed (offline).**
  `embedding_ops.balanced_pool_budget` draws EQUAL lines per member year so the label is
  the content centroid, not dragged toward a larger-corpus neighbour (F15: the raw-count
  pool made the "2018" slice 69% 2019–2020 text, centroid 2018.72 — unit-tested).
  `size_weighted_mean_year` records the centroid; `member_sets_identical` refuses to emit
  two slices from one population (news 2011/2013). **Remaining:** wire into
  `_pooled_to_tempfile`; apply the cap identically across corpora.
- [x] **#50 — determinism resolved (evidenced).** D3 harness showed `workers=1` gives
  exactly 0.0 drift; `workers=16`+seed manufactures ~0.0024. **Remaining:** set
  `_train(workers=1, seed=…)` in the rebuild — a one-line config change, not new code.
- [x] **#51 — per-era reliability floor landed + calibrated (offline).**
  `embedding_ops.is_reliable(count, floor)` gates neighbour lists / drift; unit-tested.
  [`validate_reliability_floor.py`](pipelines/analysis/validate_reliability_floor.py)
  measured the floor empirically on real news models — SNR by count band: 5–20 → **1.45**,
  20–50 → 1.75, 50–100 → **2.13**, 100–300 → 2.32. Noise drops with frequency (0.071→0.037)
  exactly as predicted. **Floor: count ≥20 for drift; the existing `neighbor_min_count=50`
  (SNR 2.1) is confirmed safely conservative.** **Remaining:** apply the gate when
  repopulating `semantic_neighbors`/`diachronic_drift`.

---

## Discussion points — need a maintainer decision

Not bugs to fix silently; these are scope and philosophy calls.

- [x] **D1 — Proper names: SPLIT into their own namespace (Phase 2, 2026-07-22).** 76.0%
  of lemmas are names (355,575 of 463,411); the honest lexicon is **107,836 content
  lemmas**. Resolved by tagging `lemmas.lemma_class` ('content'|'name') —
  `classify_lemma_class.py` (pos='name' OR every sense a name gloss; a word that is *also*
  a real word stays content). `/api/search` now routes names to a separate `name_results`
  list so surnames never crowd out real words; `/api/stats` reports the content count;
  the search page shows names under a de-emphasized «Κύρια ονόματα» group. Wired into
  ingest + a standalone backfill (run on the current DB); the rebuild picks it up.
  8 tests. Verified: «Παπαδόπουλος» → name_results only; «νόμος» → νόμος + νομός as content.
- [?] **D2 — Scope discipline.** 14 word-page surfaces and 20 pipelines against 2 measured
  quality numbers (F54). Which surfaces earn their keep?
  <sub>Audit §5 "What to CUT" has a concrete proposal.</sub>
- [?] **D3 — Diachronic claims. EVIDENCE IN (2026-07-22); recommendation FIX+KEEP,
  awaiting maintainer confirmation.** The `~96% noise` framing (F7/F12) came from the
  *shipped* DB's artifacts. The offline no-change-control harness
  (`pipelines/analysis/drift_signal_test.py`, Dubossarsky 2017) re-measured it cleanly on
  the materialized slices, at decision-grade sample sizes:
    - **Signal is real, and scales with gap width + corpus size.** News noise floor
      (two disjoint halves of one year, zero elapsed time): median 0.0795, p95 0.169.
      Real drift 2011→2024 (13 y): median 0.158, **SNR 1.98, 43.8% of words clear the
      noise p95**; 2016→2024 (8 y): SNR 1.29, 13.2%. Parliament (30k samples): 1990→2019
      SNR 1.73 / 25.1%; 2000→2019 SNR 1.60 / 20.9%.
    - **But the per-word noise floor is high** (median 0.08 news / 0.11 parliament), so a
      raw per-word drift number is mostly noise for the *typical* word — only the top
      ~20–44% (widest gaps, larger corpus) are individually trustworthy.
    - **F44/F50 nondeterminism is real but small**: `workers=1` gives exactly 0.0 drift;
      `workers=16` (the production setting) manufactures mean 0.0024 (news) / 0.005
      (parliament) even with a fixed seed — ~2–3% of the signal. Fix = `workers=1`+seed.
  **Recommendation:** FIX + KEEP, not demote/remove. The 8–10 h Tier B rebuild is worth
  it *after* the methodology waves land, repopulated with (a) a **per-word noise-floor
  gate** — surface drift only when it clears the corpus empirical p95 (news ≥0.17,
  parliament ≥0.25; this is the #51 deliverable, now with a measured threshold),
  (b) `workers=1`+seed, (c) rank/aggregate framing over precise per-word values, (d) a
  preference for wide endpoints + full 1M-line news years. The Phase 1′ honesty gates
  (drift shown only with its CI; ungated change-point suppressed) are *vindicated* by
  this — they are exactly the containment a signal this noisy needs. Full reports:
  `data/analysis/drift_signal_{news,parliament}.json` (gitignored; regenerate with the
  harness).
- [?] **D4 — "Η ΤΝ εξηγεί· οι πηγές ορίζουν".** The repo contains no LLM; the "AI" is
  word2vec + logistic regression (F31, audit §3.9). Either build the grounded-explanation
  layer the principle promises, or change the user-facing copy.
- [?] **D5 — Corpus register.** Parliament + news are both formal written Greek (F38).
  A general-purpose dictionary making frequency and change claims from them is a stretch.
  Add a spoken/informal axis, or scope the claims.
- [?] **D6 — Redistribution of corpus text.** 276,769 verbatim news sentences are
  redistributed and the per-sentence publisher file is never read (F25). Needs a legal
  review before any public release.

---

## Done

One line per shipped item with a date; full detail goes to `HANDOFF.md`.

- [x] 2026-07-21 — Adversarial methodology audit (143 agents, 63 findings) →
  `docs/AUDIT.md`.
- [x] 2026-06 — #1 accent-folding fixed in the *analysis layers*; #2 BH-FDR on trend and
  drift significance.
  <sub>Note: #1 fixed the analysis layers but **not** the lemma primary key — that is
  R2/F21, still open.</sub>
- [x] 2026-06 — #45/#46 read-side stats (Theil–Sen + Mann–Kendall; Dunning G² + Log Ratio)
  live on cache miss.
- [x] #28 Greeklish vowel expansion · #29 saved words/history · #30 audio (link-out) ·
  #31 dispersion-aware keyness · #32 paradigm engine · #33 WordNet/OMW densification ·
  #34 multi-hop etymology + cognates · #35 trajectory/change-point drift · #36 drift CIs ·
  #37 pooled slice training · #38 supervised domain attribution · #39 bilingual el↔en.

---

*Maintenance: when an item ships, flip it to `[x]` with a date and move the detail to
`HANDOFF.md`. Keep this file the only place new work is recorded.*
