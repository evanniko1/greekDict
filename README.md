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
pytest tests/ -q                 # 15 tests: normalization + end-to-end resolution
```

The end-to-end test ingests `tests/fixtures/mini_el.jsonl`, builds the index,
and asserts `ανθρώπων → άνθρωπος`. No network required.

## Running against real data

The Kaikki Greek dumps are large (~100 MB each). **Do not pull them through an
AI session** — download and ingest them yourself in a terminal:

```bash
pwsh pipelines/download_data.ps1                       # fetch el + en extracts
python pipelines/ingest/ingest_kaikki.py --input data/raw/el-extract.jsonl --source el-wiktionary --limit 5000
python pipelines/ingest/ingest_kaikki.py --input data/raw/en-extract.jsonl --source en-wiktionary --limit 5000
python pipelines/ingest/build_search_index.py
uvicorn services.api.app.main:app --reload
```

Drop `--limit` for a full run once a sample looks right. `el` first, then `en`
(en merges onto existing lemmas by normalized-lemma + POS).

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
