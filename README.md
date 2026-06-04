# Λεξόραμα

A free, open-data, **graph-first visual dictionary for Modern Greek**. Not a
prettier Wiktionary — a *lemma-resolution engine + lexical graph*. The two
features that justify the project:

1. **Form → lemma resolution that explains the form.** Type `ανθρώπων` and get
   `ανθρώπων → άνθρωπος (genitive, plural)`, then the full lemma page.
2. **A graph where every edge is typed and sourced** (synonym / derived /
   semantic — never a decorative blob).

This repo is the **M0/M1 backend spike**: Greek normalization, Kaikki ingest,
SQLite store, and a FastAPI search/word API. Frontend (Vite+React+Cytoscape),
paradigm engine, and the graph land in later milestones.

## Quickstart (no download needed to see it work)

```bash
python -m pip install -r requirements.txt
pytest tests/ -q                 # 19 tests: normalization + e2e resolution + attribution
```

The end-to-end test ingests `tests/fixtures/mini_el.jsonl`, builds the index,
and asserts `ανθρώπων → άνθρωπος`. No network required.

## Running against real data

The Kaikki Greek dumps are large (~100 MB each). **Do not pull them through an
AI session** — download and ingest them yourself in a terminal:

```bash
powershell pipelines/download_data.ps1                 # fetch el + en extracts
python pipelines/ingest/ingest_kaikki.py --input data/raw/el-extract.jsonl --source el-wiktionary --limit 5000
python pipelines/ingest/ingest_kaikki.py --input data/raw/en-extract.jsonl --source en-wiktionary --limit 5000
python pipelines/ingest/build_search_index.py
python -m uvicorn services.api.app.main:app --reload --port 8011
```

Drop `--limit` for a full run once a sample looks right. `el` first, then `en`
(en merges onto existing lemmas by normalized-lemma + POS).

**Serve on `--port 8011`, not the default 8000** — in this workspace port 8000 is
held by another app, so 8000 silently hits the wrong server. Confirm
`/api/health` reports `db: ...\data\db\lexorama.sqlite`. (`uvicorn` is invoked as
`python -m uvicorn` since it may not be on PATH.) Form-of stub entries like the
standalone `ανθρώπων` Wiktionary page are skipped at ingest, so the true lemma
resolution (`ανθρώπων → άνθρωπος`) ranks first instead of a competing stub.

Try it: `GET /api/search?q=ανθρώπων`, `GET /api/word/λόγος`, `GET /api/health`.

## Layout

```
pipelines/ingest/  normalize_greek.py · schema.sql · ingest_kaikki.py · build_search_index.py
services/api/app/  main.py  (FastAPI: /api/search, /api/word, /api/word/.../graph)
tests/             test_normalization.py · test_pipeline_e2e.py · fixtures/
apps/web/          (frontend — later milestone)
docs/              data_sources.md · licensing.md
```

## Licensing

Lexical content derives from Wiktionary (**CC BY-SA + GFDL**): attribution and
share-alike apply to the derived database. See `docs/licensing.md`. The
Triantafyllides, Academy of Athens, and e-lexicon dictionaries are **reference
/ link-out only — never ingested.**
