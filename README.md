# Λεξόραμα

A free, open-data, **graph-first visual dictionary for Modern Greek**. Not a
prettier Wiktionary — a *lemma-resolution engine + typed lexical graph + corpus
analytics layer*. Three things justify the project:

1. **Form → lemma resolution that explains the form.** Type `ανθρώπων` and get
   `ανθρώπων → άνθρωπος (genitive, plural)`, then the full lemma page.
2. **A graph where every edge is typed and sourced** — synonym / derived /
   hypernym / cognate, each carrying its provenance, never a decorative blob.
3. **Diachronic & register analytics over real corpora** — how a word's frequency,
   meaning (semantic drift), and register-distinctiveness change over time, with
   honest statistics and uncertainty attached.

Guiding principle: **sources define.** There is no language model in this product; the
only computed additions are a statistical domain classifier and a rule-based paradigm
engine, both marked wherever they surface. Every sense, form, relation,
and corpus statistic carries a `source`; nothing silently merges Wiktionary,
WordNet, corpus evidence, and inferred labels.

## Status

Full-stack and working locally: Greek normalization → Kaikki/Wiktionary ingest →
SQLite store → FastAPI → Vite/React/Cytoscape frontend, plus a generative paradigm
engine, multi-hop etymology, KWIC concordances, WordNet/OMW edges, bilingual el↔en,
and the **Layer B/C** corpus pipelines (frequency time-series + diachronic semantic
drift, trends, keyness, and a supervised domain classifier). **88 passing tests.**

What's *not* done yet lives in [`BACKLOG.md`](BACKLOG.md) — the single source of truth
for every bug, critical issue, feature and open question, including the 63 findings of
the [methodology audit](docs/AUDIT.md). The running session log / decision record is
[`HANDOFF.md`](HANDOFF.md).

## Quickstart (no download needed)

```bash
python -m pip install -r requirements.txt
pytest tests/ -q          # 88 tests: normalization, e2e resolution, attribution,
                          #   pooling, change-point, drift CIs, trends, keyness, …
```

The e2e test ingests `tests/fixtures/mini_el.jsonl`, builds the index, and asserts
`ανθρώπων → άνθρωπος`. No network required.

## Run the app (against the real DB)

The API and web dev server are pinned to **8011** and **5180** (8000/5173 are held
by another app in this workspace). On Windows, one launcher starts both and opens
the browser:

```bat
scripts\start-lexorama.bat        :: API :8011 + web :5180, leaves a running one alone
```

Or manually:

```bash
# API (stop it before any write-ingest — SQLite WAL holds the DB)
python -m uvicorn services.api.app.main:app --port 8011 --app-dir .

# Web
cd apps/web && npm install && npm run dev    # http://localhost:5180
```

Confirm `GET /api/health` reports `db: ...\data\db\lexorama.sqlite`. On Windows set
`PYTHONIOENCODING=utf-8` for any Greek-handling script (cp1252 otherwise crashes).

## Building the data

Dumps are large (~100 MB) — **download and ingest in your own terminal, never
through an AI session.** Stop the API first; every write-pipeline holds the WAL DB.

```bash
# 1. Core lexicon (el first, then en — en merges onto el lemmas by normalized-lemma+POS)
powershell pipelines/download_data.ps1
python pipelines/ingest/ingest_kaikki.py --input data/raw/el-extract.jsonl --source el-wiktionary
python pipelines/ingest/ingest_kaikki.py --input data/raw/en-extract.jsonl --source en-wiktionary
python pipelines/ingest/build_search_index.py        # full rebuild; safe to re-run

# 2. Enrichment (graph + word page)
python pipelines/ingest/ingest_wordnet.py            # typed semantic edges (omw-el)
python pipelines/ingest/reparse_etymology.py         # multi-hop etymology + cognates
python pipelines/ingest/ingest_examples.py           # KWIC concordances
python pipelines/ingest/ingest_neighbors.py          # static embedding neighbours
python pipelines/ingest/backfill_paradigms.py        # generative κλίση/conjugation

# 3. Layer B/C corpus analytics (per corpus, on its OWN axis — never merged)
python pipelines/ingest/ingest_frequency_timeseries.py --leipzig-dir data/raw --leipzig-source ell_news
python pipelines/ingest/ingest_frequency_timeseries.py --parliament-csv data/raw/Greek_Parliament_Proceedings_1989_2020.csv
python pipelines/ingest/ingest_diachronic.py --leipzig-dir data/raw --leipzig-source ell_news --pool-window 2
python pipelines/ingest/ingest_diachronic.py --parliament-csv data/raw/Greek_Parliament_Proceedings_1989_2020.csv --pool-window 2
python pipelines/ingest/bootstrap_drift.py --corpus news       --k 100 --pool-window 2
python pipelines/ingest/bootstrap_drift.py --corpus parliament --k 100 --pool-window 2
python pipelines/ingest/classify_domains.py          # distant-supervision domain classifier
```

Use `--limit` on the Kaikki ingest to validate on a sample first. `bootstrap_drift`
at `--k 100` is an overnight job (retrains word2vec K times per anchor).

## Architecture

```
pipelines/ingest/   normalize_greek.py · schema.sql · ingest_kaikki.py · build_search_index.py
                    corpus_sources.py · ingest_frequency_timeseries.py        (Layer B)
                    ingest_diachronic.py · bootstrap_drift.py · classify_domains.py  (Layer C)
                    paradigm_engine.py · ingest_wordnet.py · reparse_etymology.py
                    ingest_examples.py · ingest_neighbors.py · build_gloss_index.py · …
services/api/app/   main.py            (FastAPI — see API surface below)
apps/web/           Vite + React + TS + Tailwind v4 + react-router + Cytoscape
tests/              88 tests (normalization, e2e, pooling, change-point, drift CIs,
                    trends, keyness, anchored alignment, domains, …)
docs/               data_sources.md · licensing.md · AUDIT.md
BACKLOG.md          single source of truth for open work (bugs, features, decisions)
scripts/            start-lexorama.{bat,ps1}
```

- **Normalization is one function.** `normalize_greek.normalize()` builds *all*
  search keys (folds case/accent/final-sigma/dialytika). Display keeps accents
  (accent is phonemic: πότε ≠ ποτέ, νόμος ≠ νομός); only the lookup key folds.
  Analysis layers key on `normalize_keep_accents()` so homographs stay distinct.
- **Layer B** = `frequency_timeseries` (per-million usage over time per corpus).
  **Layer C** = diachronic semantic drift + trajectory + era-neighbours + bootstrap
  CIs + the domain classifier. Each corpus stays on its **own axis** — Parliament
  and news are never merged into one space (Procrustes alignment across registers
  is meaningless).

## API surface

```
GET /api/search?q=…                  form→lemma resolution (+ Greeklish, en→el)
GET /api/word/{lemma}                 senses, forms, paradigm, etymology, KWIC, neighbours
GET /api/word/{lemma}/graph           typed + sourced relation graph
GET /api/word/{lemma}/diachronic      per-axis frequency, drift, trajectory, era-neighbours
GET /api/explore/overview             corpus stats landing
GET /api/explore/trends               rising/falling usage (Theil–Sen + Mann–Kendall + FDR)
GET /api/explore/compare              cross-corpus drift agreement + keyness (G² + Hardie LR)
GET /api/explore/by-field             vocabulary by subject domain
GET /api/explore/interesting          curated highlights
GET /api/insights/drift · /queries    methodology insights + query-log flywheel
GET /api/attributions · /api/health
```

Frontend pages: **Search**, **Word**, **Explore** (corpus analytics), **Methodology**
(every statistic is explained in-app), **About**, **Licensing**.

## Methodology

Diachronic drift uses per-slice word2vec aligned with **orthogonal Procrustes**
(Hamilton et al. 2016, anchored on stable high-frequency words), **Gonen et al.
2020** neighbour-overlap as a frequency-robust change measure, **Benjamini–Hochberg
FDR** for multiple comparisons, **Theil–Sen + Mann–Kendall (Hamed–Rao)** for usage
trends, **Dunning G² + Hardie Log Ratio** for keyness, and a distant-supervision
logistic-regression **domain classifier** (calibrated, with an abstain option). The
in-app `/methodology` page documents each in Greek; see [`BACKLOG.md`](BACKLOG.md) for
the limits we haven't closed yet — several are serious and currently overstated on that
page (see [`docs/AUDIT.md`](docs/AUDIT.md) §6).

## Licensing

Lexical content derives from Wiktionary (**CC BY-SA + GFDL**) and Greek WordNet/OMW
(**Apache-2**): attribution and share-alike apply to the derived database. See
[`docs/licensing.md`](docs/licensing.md). The Triantafyllides, Academy of Athens
Χρηστικό Λεξικό, and e-lexicon dictionaries are **reference / link-out only — never
ingested.**
