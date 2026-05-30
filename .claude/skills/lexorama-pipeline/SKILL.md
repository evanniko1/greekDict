---
name: lexorama-pipeline
description: Run and reason about the Λεξόραμα Greek-dictionary data pipeline (Kaikki ingest, search index, normalization invariants) and enforce its licensing + provenance guardrails. Use whenever ingesting lexical data, adding a data source, touching normalize_greek, or building search/word endpoints in C:\dev\greekDict.
---

# Λεξόραμα pipeline

Λεξόραμα is a free, open-data, graph-first Modern Greek dictionary. Its value is
**form→lemma resolution that explains the form** and a **typed, sourced graph**.

## Invariants — do not break

1. **One normalization function.** `pipelines/ingest/normalize_greek.normalize()`
   is the single source of search keys (folds accent/case/final-sigma/dialytika/
   polytonic). Anything that builds or queries `search_index` MUST key through it.
   Never hand-roll folding elsewhere.
2. **Display preserves accents; keys fold them.** Accent is phonemic in Greek
   (πότε vs ποτέ). Store the accented surface for display, the folded key for
   lookup. Disambiguate accent-homographs at ranking, not in `normalize`.
3. **Provenance per item.** Every sense/form/relation carries a `source`. Never
   silently merge Wiktionary, WordNet, corpus, or AI content. AI explains;
   sources define.

## Licensing gate — blocking

Before ingesting ANY new source, confirm its license permits reuse + share-alike.
- ALLOWED: Wiktionary/Kaikki (CC BY-SA + GFDL), Greek WordNet/OMW (Apache-2).
- **FORBIDDEN — link-out only, never ingest text:** Triantafyllides
  (greek-language.gr), Academy of Athens Χρηστικό Λεξικό, e-lexicon.gr.
If a source isn't clearly reusable, stop and ask. Record attribution in
`source_attributions` and `docs/licensing.md`.

## Token economy — large dumps

Kaikki dumps are ~100 MB. They are processed by **streaming** in
`ingest_kaikki.py`, line by line. NEVER `Read` a dump into context. To inspect,
use `head`-limited samples or SQLite `COUNT`/`SELECT ... LIMIT`. The user runs
the download (`pipelines/download_data.ps1`) in their own terminal.

## Standard run order

```bash
# 1. user downloads (terminal, not via model):
pwsh pipelines/download_data.ps1
# 2. ingest el first, then en (en merges onto el lemmas by normalized_lemma+pos):
python pipelines/ingest/ingest_kaikki.py --input data/raw/el-extract.jsonl --source el-wiktionary --limit 5000
python pipelines/ingest/ingest_kaikki.py --input data/raw/en-extract.jsonl --source en-wiktionary --limit 5000
# 3. rebuild the lookup surface:
python pipelines/ingest/build_search_index.py
# 4. serve + verify:
uvicorn services.api.app.main:app --reload   # GET /api/search?q=ανθρώπων
```
Use `--limit` to validate on a sample before dropping it for a full run.
`build_search_index` is a full rebuild (DELETE + repopulate) — safe to re-run.

## Validate after any pipeline change

```bash
pytest tests/ -q   # 15 tests: normalization + e2e form→lemma resolution
```
The e2e test (`tests/test_pipeline_e2e.py`) runs against `tests/fixtures/
mini_el.jsonl` with no download — keep it passing.
