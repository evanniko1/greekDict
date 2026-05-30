# Session handoff — start here

This file orients a fresh Claude Code session opened in `C:\dev\greekDict`.
(Project memory at `~/.claude/projects/C--dev-greekDict/memory/MEMORY.md` also
auto-loads — read it for full context.)

## What this is
**Λεξόραμα** — free, open-data, graph-first visual dictionary for Modern Greek.
The two features that justify the project:
1. Form → lemma resolution that *explains the form* (`ανθρώπων → άνθρωπος,
   genitive plural`).
2. A graph where every edge is typed + sourced.

## State (as of 2026-05-30)
M0/M1 backend spike is built, committed, and green (15 tests). Working:
- `pipelines/ingest/normalize_greek.py` — accent/case/final-sigma/dialytika/
  polytonic folding; lossy greeklish candidate generator.
- `pipelines/ingest/schema.sql`, `ingest_kaikki.py` (streaming, el+en merge),
  `build_search_index.py`.
- `services/api/app/main.py` — FastAPI `/api/search` (with match explanation),
  `/api/word`, `/api/word/.../graph` (stub).
- e2e test resolves `ανθρώπων → άνθρωπος` from a synthetic fixture, no download.

`fastapi` is installed in the user's Python 3.12. `pytest tests/ -q` = 15 pass.

## Immediate next steps (this session)
1. **Download real data** — the user runs this in a terminal; the dumps are
   ~100 MB and must NOT pass through the model:
   ```
   pwsh pipelines/download_data.ps1
   ```
   (Verify current URLs at https://kaikki.org/ first — Kaikki paths change.)
2. **Ingest a sample, then full**, then index:
   ```
   python pipelines/ingest/ingest_kaikki.py --input data/raw/el-extract.jsonl --source el-wiktionary --limit 5000
   python pipelines/ingest/ingest_kaikki.py --input data/raw/en-extract.jsonl --source en-wiktionary --limit 5000
   python pipelines/ingest/build_search_index.py
   ```
   The model should only inspect `head`-limited samples / row counts — never the
   dump body.
3. **Verify** against real data: `uvicorn services.api.app.main:app --reload`,
   then `GET /api/search?q=ανθρώπων`, `/api/word/λόγος`, `/api/health`.

## Known gaps / next builds
- **Greeklish is lossy on vowels** (o↔ω, i↔η↔υ). `anthropon` does NOT resolve
  yet. Fix = multi-candidate vowel expansion in `normalize_greek` (generate
  every vowel variant, match any) OR plug in GR-NLP-TOOLKIT. Good first task.
- **Paradigm engine** (rule-based declension/conjugation) — confirmed decision,
  so morphology tables are complete, not just source forms.
- **Graph (M4)** — WordNet typed edges + embeddings for sparsity.
- **Frontend** — Vite+React+TS+Tailwind+Cytoscape, mobile tabs.

## Hard rules
- Never ingest Triantafyllides / Academy of Athens / e-lexicon — link-out only.
- Every displayed item keeps its `source`. AI explains; sources define.
- See `.claude/skills/lexorama-pipeline/SKILL.md` for the enforced checklist.
