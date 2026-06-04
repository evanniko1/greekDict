# Backlog — not yet implemented

A running, honest list of what Λεξόραμα does **not** do yet. Grouped into
data/graph depth and infrastructure. Each item notes why it matters and a
rough sense of effort. This is a planning doc, not a promise of order. (The whole
methodology track — drift CIs, pooling, supervised domain attribution — has shipped.)

Shipped items are removed from here and recorded under HANDOFF.md "Done" (see the
maintenance note at the bottom). Most recently shipped: #28 Greeklish vowel
expansion, #29 saved words/history, #30 audio (link-out), #31 dispersion-aware
keyness, #32 paradigm engine, #33 graph densification (WordNet/OMW), #34 multi-hop
etymology + cognates, #35 trajectory/change-point drift, #36 drift CIs/significance
(bootstrap) + trend slope significance, #37 pooled (±2-yr) slice training,
#38 supervised domain attribution (distant-supervision skip-gram classifier),
#39 bilingual el↔en (English glosses on word pages + en→el cross-language search).

---

## 1. Data & graph depth

- **More corpora on their own axes (#40) — pipeline shipped; awaiting data.** The
  ingest path now supports any number of Leipzig corpora side-by-side under one
  directory, each on its **own** axis (never merged): `--leipzig-source` scopes
  Layers B & C to one source, the axis label is derived from the folder prefix
  (`ell_wikipedia_*` → `wiki`), and the word page + Εξερεύνηση surface new axes
  automatically. What's left is purely **data acquisition** — downloading and
  ingesting an actual second Leipzig corpus (Wikipedia/web) or a literary corpus;
  those dumps are large and must be pulled outside an LLM session (see
  `pipelines/download_data.ps1`). *Effort remaining:* L per corpus (download + train).

## 2. Methodology hardening (NLP / stats critique — apply next)

These came out of a strict methodology pass. #1 (accent-folding merged phonemically
distinct homographs in every analysis layer — νόμος "law" vs νομός "prefecture") and
#2 (no multiple-comparison control on trend/drift significance — Benjamini–Hochberg
FDR + q-values on trends *and* drift) are **shipped and live** (re-ingested 2026-06).

Ordered by leverage, not number. **Wave 1** fixes what we *label* significant across
the whole app; **Wave 2** removes the bias at the source of every drift number;
**Wave 3** retires "stated-as-fact" overclaims; **Wave 4** is refinement.

> **Status (2026-06):** all nine are now implemented + unit-tested. The two read-side
> fixes — **#45** (Theil–Sen + Mann–Kendall/Hamed–Rao trends) and **#46** (Dunning G² +
> Hardie Log Ratio keyness) — are **live** (recompute on cache miss, no re-ingest). The
> seven pipeline-side fixes — **#43/#44/#47/#48/#49/#50/#51** — are **code-complete and
> awaiting the batched overnight re-run** (`pipelines/ingest/_reingest_methodology_waves.sh`;
> bootstrap K=100 ≈ 8–10h). They also fixed a latent bug: after #1, `bootstrap_drift`
> still keyed on the accent-folded form, so significance reached only ~6% of lemmas. The
> notes below are the original audit baselines; remove each item once the run lands it.

### Wave 1 — significance labelling (contained stats changes)

- **Bootstrap K=12 is too few (#43).** *Have:* `bootstrap_drift.py` runs K=12 and the
  per-lemma test is now a parametric z vs. the frequency-matched control null → BH-FDR
  (came in with #2). *Missing:* the count itself — move to K≥100 via **BCa or a
  permutation test** (resample sentences/tokens within slices, not just the slice
  set). Code comment at L246 already flags this as the deferred refinement. *Effort:* M.

- **Trend slope p-values assume i.i.d. years (#45).** *Have:* min-year gate
  (`HAVING n>=min_n`), an R²≥0.25 shape gate, and BH-FDR on the slope p (#2). *Missing:*
  the autocorrelation-robust inference that is the actual point — **Newey–West HAC**
  SEs or a **Mann–Kendall** test (OLS i.i.d. t-test makes short autocorrelated series
  anti-conservative), and enforce n≥5–6. Scaffolding exists; this is the layer on top.
  *Effort:* M.

### Wave 2 — bias at the source

- **Procrustes alignment is fit on the full shared vocabulary (#48).** *Have:*
  `_align()` (`ingest_diachronic.py` L219) fits `orthogonal_procrustes` over **all**
  shared words, so the words that actually drift pull the rotation and contaminate
  everyone's measured drift. *Missing:* anchor the alignment on **stable, high-frequency
  words only** (iterative/anchored Procrustes). Biases every drift number, so it lands
  before the "stated-as-fact" fixes. *Effort:* M.

### Wave 3 — retire "stated-as-fact" overclaims

- **change_point_year is argmax over noise (#44).** *Have:* `change_point_year()`
  (L201) is pure argmax of the steepest single step, no uncertainty. *Missing:* a
  CI/null (bootstrap the change-point location) or a principled detector
  (**PELT / CUSUM / binary segmentation**); suppress/flag when indistinguishable from
  neighbours. *Effort:* M.

- **Domain classifier softmax is uncalibrated and forces a field on every word
  (#47).** *Have:* a `STORE_FLOOR=0.30` confidence floor + an API display gate (a crude
  reject) and a held-out accuracy/macro-F1 report. *Missing:* **Platt/isotonic
  calibration**, a proper **abstain option** (no field when max prob is low or the
  top-2 margin is thin), and **per-field precision** in the report. *Effort:* M.

- **Era-neighbors for rare words are noise presented as fact (#51).** *Have:* only the
  word2vec `min_count=10` training floor + token len≥3 + stopword filter. *Missing:* a
  **per-era frequency floor** below which a lemma's neighbour list is suppressed or
  flagged low-evidence — `min_count` is exactly the floor #51 argues is insufficient.
  *Effort:* S.

### Wave 4 — refinement

- **Keyness uses a raw log-ratio with an arbitrary +0.1 smoother and no variance
  model (#46).** *Have:* `log2((pm_p+0.1)/(pm_n+0.1))` (main.py L1454) gated by Gries
  DP dispersion (#31). *Missing:* a variance model — **Log-Likelihood (G²)** or
  **Hardie's Log Ratio with CIs**, separating effect size from significance. *Effort:* S–M.

- **Pooled ±2-yr training blurs boundary signal (#49).** *Have:* a fixed `--pool-window`
  (run at ±2). *Missing:* make the window **adaptive to slice density**, or report
  sensitivity to window size — the stability/temporal-resolution trade-off is currently
  fixed and unexamined. *Effort:* S–M.

- **Single seed=0 for displayed point estimates (#50).** *Have:* `seed=0`, single run
  across ingest/bootstrap/classify; the displayed drift_score is one model's output and
  not the centre of its own CI. *Missing:* **average over multiple seeds** (or report
  the bootstrap mean) for the headline number. *Effort:* S.

## 3. Infrastructure & deploy

- **Postgres + pg_trgm migration (#41).** Dev runs on SQLite. Production search (fuzzy,
  trigram, concurrent writes) wants Postgres with `pg_trgm`. Migration path and a
  deploy target are not done. *Why:* SQLite WAL forces the API to stop during
  ingest — see HANDOFF. *Effort:* L. **(infra — last)**

- **CI / automated ingest refresh (#42).** Ingest + Layer B/C re-runs are manual
  (and the API must be stopped first). A scheduled, locked refresh pipeline is
  missing. *Effort:* M. **(infra — last)**

- **Observability (part of #42).** Query-logging flywheel exists; no dashboards /
  alerting on unresolved-miss rate. *Effort:* S. **(infra — last)**

---

*Maintenance note:* when an item ships, move it to `HANDOFF.md` "Done" and delete
it here. Keep this list short and honest — it is the project's own critique.
