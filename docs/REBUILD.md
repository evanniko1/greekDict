# Corrected Tier B rebuild — runbook

The methodology waves (#43–#51) and the classifier (#47) are **wired into the pipeline**.
Running the corrected code repopulates the diachronic / keyness / classifier layers and
turns the served numbers from the audited artefacts into the recalibrated estimates. This
is the payoff step; it is an **overnight job the maintainer runs**, not a session task.

## Before you start — three things

1. **Stop the API.** It holds the WAL DB; a write-ingest will block or corrupt while it is
   up. The scripts stop it by port owner (8011).
2. **Licensing.** Tier B reintroduces the CC BY-NC Wortschatz Leipzig corpus (collocations,
   examples, semantic neighbours, diachronic) and redistributes verbatim news sentences. For
   a **non-distributed research** DB that is fine (your call); do **not** publish a snapshot
   as CC BY-SA afterward — see `DATA-LICENSE.md` / BACKLOG D6.
3. **Determinism vs speed.** `ingest_diachronic`/`_train` default to `workers=1` for a
   bit-reproducible point estimate (F44/F50). That is slow. Pass `--workers 8` to trade
   reproducibility for speed on the trajectory training if the wall-clock matters; the
   D3 harness measured the nondeterminism this reintroduces at only ~0.0024 drift.

## What the wiring changed (so you know what the rebuild materialises)

| Layer | Corrected behaviour | Wave / finding |
|---|---|---|
| word2vec training | `sg=1` (SGNS), `workers=1`+seed | #48/#44/#50 · F14/F44 |
| alignment | L2-normalized Procrustes, cosine-residual anchor pruning | #48 · F14 |
| pooling | equal lines per member year (centroid = label year) | #49 · F15 |
| change point | Pettitt test + null (location shift, not gap spike) | #44 · F5/F9 |
| drift | suppressed below the per-era reliability floor (count ≥ 20) | #51 |
| bootstrap CI | bias-corrected interval, K≥100, `drift_score_boot` stored | #43/#50 · F11/F60 |
| trends | Mann–Kendall + Hamed–Rao (read-side, live on cache miss) | #45 · F10/F39 |
| keyness | Dunning G² + BH-FDR across all tests (read-side) | #46 · F20/F43 |
| domain classifier | isotonic-calibrated + per-class abstain thresholds | #47 · F16/F17/F45 |
| lexicon | proper names split into their own namespace | Phase 2 · F37 |

Read-side waves (#45 trends, #46 keyness) need **no rebuild** — they recompute on the next
cache miss (the cache keys were bumped so stale results are not served). The rest needs the
data below.

## Sequence

The current DB is already a clean Tier A rebuild (F1–F4 fixes, homographs, names
classified), so the practical path is to run **Tier B only** on it. A from-scratch rebuild
runs Tier A first (steps 0–4).

### Tier A — lexical core (only for a from-scratch rebuild)
```
# 0. dumps already downloaded (see pipelines/download_data.ps1)
python pipelines/ingest/ingest_kaikki.py --input data/raw/el-extract.jsonl --source el-wiktionary --db data/db/lexorama.sqlite
python pipelines/ingest/ingest_kaikki.py --input data/raw/en-extract.jsonl --source en-wiktionary --db data/db/lexorama.sqlite
python pipelines/ingest/classify_lemma_class.py --db data/db/lexorama.sqlite   # names split (Phase 2)
python pipelines/ingest/build_search_index.py --db data/db/lexorama.sqlite
python pipelines/ingest/ingest_frequency.py --freq-file data/raw/el_freq.txt --db data/db/lexorama.sqlite
python pipelines/ingest/build_gloss_index.py --db data/db/lexorama.sqlite
python pipelines/ingest/ingest_wordnet.py --db data/db/lexorama.sqlite
# etymology + paradigm passes as documented in HANDOFF.md
```

### Tier B — the corrected diachronic/corpus layers (the ~8–10 h job)
`pipelines/ingest/_reingest_methodology_waves.sh` already orchestrates the core of this
(stop API → diachronic both axes → bootstrap K=100 → calibrated classifier → restart). It
now invokes the corrected code with no flag changes. Run it, or step through:
```
DB=data/db/lexorama.sqlite
NEWS="--leipzig-dir data/raw --leipzig-source ell_news"
PARL="--parliament-csv data/raw/Greek_Parliament_Proceedings_1989_2020.csv"

# Layer C — diachronic (workers=1 default; add --workers 8 for speed). ~min per axis at
# workers>1, much longer at workers=1.
python pipelines/ingest/ingest_diachronic.py $NEWS --db "$DB" --pool-window 2 --pool-adaptive
python pipelines/ingest/ingest_diachronic.py $PARL --db "$DB" --pool-window 2 --pool-adaptive

# Bootstrap CIs — K=100 + bias-corrected interval. THE expensive step (~8–10 h both axes).
python pipelines/ingest/bootstrap_drift.py --corpus parliament --k 100 --db "$DB"
python pipelines/ingest/bootstrap_drift.py --corpus news --k 100 --cap 250000 --db "$DB"

# Domain classifier — isotonic-calibrated + abstain + per-field precision.
python pipelines/ingest/classify_domains.py --db "$DB"

# The remaining corpus layers (as in HANDOFF): semantic neighbours, collocations, examples,
# frequency timeseries — run their scripts if repopulating from scratch.
python pipelines/ingest/ingest_neighbors.py --db "$DB"      # apply pos!='name' + workers=1
python pipelines/ingest/ingest_collocations.py ...          # Leipzig co-occurrence
python pipelines/ingest/ingest_examples.py ...              # KWIC examples
```

## After the run — verify it landed

```
python pipelines/ingest/manifest.py --db data/db/lexorama.sqlite
```
The divergence checker should now move toward **green** — in particular
`drift_columns` (change_point_score / drift_score_boot no longer 100% NULL) and
`classifier_floor` (rows written by the current calibrated code). Then restart the API and
spot-check `/api/word/κρίση/diachronic` and `/api/explore/compare`; the DiachronicPanel
change-point should appear only where it is statistically significant, and drift only with
its CI.

## Note on scope

`_reingest_methodology_waves.sh` re-runs the *waves* on the existing lexical DB. If you want
a single fresh artefact with a recorded build manifest end-to-end, run Tier A then Tier B in
one sitting; `manifest.record_build` stamps each producing component so provenance is
complete and the checker can pass cleanly.
