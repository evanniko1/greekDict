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

## State (as of 2026-05-31)
M0/M1 backend spike is built, committed, and green (18 tests). Working:
- `pipelines/ingest/normalize_greek.py` — accent/case/final-sigma/dialytika/
  polytonic folding; lossy greeklish candidate generator.
- `pipelines/ingest/schema.sql`, `ingest_kaikki.py` (streaming, el+en merge),
  `build_search_index.py`.
- `services/api/app/main.py` — FastAPI `/api/search` (with match explanation),
  `/api/word`, `/api/word/.../graph` (stub).
- e2e test resolves `ανθρώπων → άνθρωπος` from a synthetic fixture, no download.

`fastapi` is installed in the user's Python 3.12. `pytest tests/ -q` = 15 pass.

## Done this session (2026-05-30)
Real Kaikki dumps downloaded by user (URLs verified live), sample-ingested, and
verified end-to-end on real data:
- el-extract.jsonl (1.4 GB / 1.75M lines, multilingual el-edition) + en-extract
  .jsonl (202 MB / 85k lines, Greek entries). URLs in download_data.ps1 confirmed
  current via HEAD checks.
- `--limit 5000` ingest: el → 1888 Greek lemmas (3112 non-Greek skipped); en →
  5000 lemmas (0 skipped). build_search_index → 82,348 keys (5,873 lemma + 76,475
  form; el+en lemmas merged 6,888→5,873 by normalized_lemma+pos).
- `GET /api/search?q=ανθρώπων` → resolved:true, `ανθρώπων → άνθρωπος (genitive,
  plural)` (match_type inflected_form). `/api/word/λόγος` returns full declension.

### Environment gotchas hit (read before re-serving)
- **uvicorn was NOT installed** (only fastapi was). Installed uvicorn 0.48.0 into
  the user's Python 3.12.8. `uvicorn ...` bare fails (not on PATH) — use
  `python -m uvicorn`.
- **Port 8000 is occupied by a FOREIGN app** (`wcecoli.db` / reconstruction — the
  surrounding nrps-chemspace-explorer workspace). Serving on 8000 silently hits
  the wrong server. **Use 8011** (or any free port) and confirm `/api/health`
  reports `db: C:\dev\greekDict\data\db\lexorama.sqlite`.
- Windows console is cp1252: set `PYTHONIOENCODING=utf-8` and read dump files
  with `open(..., encoding='utf-8')` — piping `head | python` mis-decodes Greek
  and gives false negatives.
- Serve command (verified):
  `python -m uvicorn services.api.app.main:app --port 8011`

## Done this session (2026-05-31)
- **Form-of ranking quirk FIXED.** `ingest_kaikki.is_form_of_entry()` skips
  entries whose every sense is a form-of pointer (structured `form_of` field or
  `"form-of"` sense tag), so the standalone `ανθρώπων` page no longer becomes a
  competing lemma. Verified across the full el dump: this conservative signal
  drops 337k pure stubs but spares 913 entry-tag-only words (μηδέν/σε/λίγο) that
  carry a real sense — no legitimate lemma lost. New stat `form_of_skipped`.
  Regression test `test_form_of_stub_not_a_competing_lemma` + fixture stub added.
  `/api/search?q=ανθρώπων` (port 8011) now returns a single `inflected_form`
  result, `ανθρώπων → άνθρωπος (genitive, plural)`.
- README + this skill's validation gate updated (15 → 16 tests; serve-on-8011).
- **`relations` table now populated.** `ingest_kaikki.extract_relations()` pulls
  synonyms/antonyms/related/derived/hypernyms/hyponyms/coordinate_terms from both
  entry- and sense-level lists (each `{"word": ...}`), mapped to typed
  relation_type + source; `resolve_relation_targets()` links target_text →
  target_lemma_id by normalized surface (idempotent across el/en passes). Sample
  (300k el lines): 144,863 relations, 99,140 resolved. `/api/word/λόγος/graph`
  now returns real typed+sourced edges (was an empty stub). +1 test (17 total).
  NOTE: the graph endpoint returns `target_text` but not yet `target_lemma_id` —
  surface it in Phase 4 so resolved nodes are clickable.
- **Frontend prototype (Phases 1–3) built** in `apps/web` (Vite+React+TS+
  Tailwind, react-router). Search→resolution card→word page, verified in browser
  against the live API. Dev server pinned to **:5180 strictPort** (5173 is taken
  by the foreign app, like 8000). `.claude/launch.json` drives the preview tool.
- **Frontend Phases 4–5 DONE — full prototype complete.** Cytoscape graph view
  (`RelationGraph.tsx`): typed+sourced edges, modern harmonised 600-weight
  palette, `cose` layout with `nodeDimensionsIncludeLabels`+white label halo so
  words don't pile up; resolved targets get a white ring + pointer + click-to-
  open, unresolved ones render muted. Mobile tabs (Ορισμοί / Κλίση / Σχέσεις) via
  a `useMediaQuery` hook — only ONE layout tree mounts, so the graph never mounts
  in a `display:none` container (avoids 0×0 cytoscape) and runs one API call.
- **Junk relation targets filtered at ingest.** `_is_junk_target()` drops
  Wiktionary category prose (non-breaking space `\xa0`, newline, or `Βικιλεξικ`
  self-reference) so the graph has no fake nodes. Test
  `test_junk_relation_targets_filtered` (18 total). Test DB rebuilt clean.
- **Κλίση grouped into Greek paradigm tables + English purged.** New
  `apps/web/src/api/inflection.ts` (`buildInflection`) buckets the flat en-wiktionary
  form list into proper grids: verbs → one table per voice (Ενεργητική/Παθητική),
  columns = tense/mood (Ενεστώτας/Παρατατικός/Αόριστος/Εξαρτημένος/Προστακτική),
  rows = person×number; nominals → number×case, split by gender. `expandHeadword()`
  recovers the "canonical" lemma row (which carried a trailing Latin annotation like
  "υπολογίζω active") into its correct cell instead of dropping it, and skips
  romanization rows. Anything unmatched falls through to "Άλλοι τύποι" (never lost),
  rendered by `InflectionTables.tsx` with a per-grid "Πηγή:" footnote. All feature
  tags translated via extended `labels.ts` (participle→μετοχή, infinitive→απαρέμφατο,
  progressive/continuative→εξακολουθητικός, etc.). Verified on /word/υπολογίζω: zero
  English in grids or leftover table.
- **Definitions are Greek-only.** `EntryDefinitions` now prefers el-wiktionary senses
  (`source startsWith "el"`) and only falls back to en glosses when a lemma has NO
  Greek sense. Bilingual el+en data stays in the DB for a future Greek↔English mode.
- **Full Greek UI localisation.** `apps/web/src/api/labels.ts` maps Wiktionary's
  English enums to Greek for display only (keys stay English): pos (ουσιαστικό…),
  gender (αρσενικό…), match_type (κλιτός τύπος…), relation_type (συνώνυμο…), and
  grammatical features/tags (γενική, πληθυντικός, αρσενικό…). All chrome strings
  translated (Αναζήτηση, Κλίση, Σχέσεις, Φόρτωση…). Unknown values fall back to
  raw so nothing disappears.

## Immediate next steps
1. **Full ingest** (drop `--limit`) once satisfied with the sample, then rebuild
   the index. Same commands, no `--limit`. Inspect only via COUNT / LIMIT.
   NOTE: re-running ingest now also refreshes `source_attributions.retrieved_at`.

## Done this session (2026-05-31, cont.)
- **Code-split cytoscape.** `WordPage` lazy-loads `RelationGraph` (React.lazy +
  Suspense). Initial JS 686→252 kB (gzip 80); graph in its own 438 kB chunk,
  fetched only when the Σχέσεις panel shows. >500 kB build warning gone.
- **`source_attributions` compliance gate CLOSED.** `ingest_kaikki.record_attribution()`
  upserts one row per source (source_url, license "CC BY-SA 4.0 / GFDL",
  modification notice, `retrieved_at`) on every ingest — idempotent, keyed by
  source_name. New `GET /api/attributions`. Frontend: persistent **site footer**
  on every page (so deep-linked word pages carry the notice) → links to new
  **`/licensing`** page (full CC+GFDL text, source links, ShareAlike statement),
  driven by the API. Per-item `source` badges unchanged (provenance ≠ legal
  notice). +1 test `test_source_attribution_recorded` (19 total). `docs/licensing.md`
  updated with the implemented design.
  - GOTCHA: `uvicorn --reload` spawns a `multiprocessing-fork` **worker** child
    whose command line is `spawn_main(...)`, NOT `uvicorn`. Killing by
    command-line match leaves orphaned workers holding :8011, so new launches
    silently fail to bind and you keep hitting stale code. Kill by **port owner**
    (`Get-NetTCPConnection -LocalPort 8011`) or just run without `--reload`.
    Live test DB backfilled with both attribution rows.

- **Web design pass: LLM-style landing + light/dark theme.** Landing (`SearchPage`)
  now has a calm, centered foundation-model-style hero (large wordmark, tagline,
  prominent search field with icon, example-query chips) that collapses into the
  results view once you type. Full **light/dark mode** with remembered preference:
  Tailwind v4 class-based dark variant (`@custom-variant dark` in `index.css`, no
  config file); `useTheme` hook (localStorage `lexorama-theme`, follows OS until
  the user picks); pre-paint inline script in `index.html` prevents FOUC; sun/moon
  `ThemeToggle` in the header. Every surface got `dark:` variants (App shell,
  search, ResultCard, WordPage, InflectionTables, Footer, LicensingPage). The
  cytoscape graph can't use Tailwind classes, so a read-only `useIsDark()` hook
  (MutationObserver on the `<html>` class — avoids a 2nd `useTheme` desyncing from
  the header) drives theme-aware label/halo/muted colours, recomputed on toggle.
  Also de-emphasised: the raw `score` number was removed from `ResultCard` (internal
  ranking, not user-facing). Build clean, graph still code-split.

## Done this session (2026-05-31, cont. 2)
- **Layout widened + heading dedup.** App shell/header/footer/main now `max-w-5xl`
  (was `max-w-3xl`) so the graph + inflection tables breathe; the definitions
  reading column is re-capped at `max-w-3xl` for legibility. The repeated lemma
  heading on the Κλίση card now shows only when `entries.length > 1`
  (`EntryForms` gained a `showLemma` prop) — no more double headword on the
  common single-entry page.
- **English-terminology audit done.** Extended `labels.ts` GRAM_EL with ~70 more
  Greek mappings for tags surfaced by a DB audit (type-a→α' συζυγία, indeclinable→
  άκλιτο, deponent→αποθετικό, dual→δυϊκός, strong/weak→δυνατός/αδύνατος τύπος,
  katharevousa/demotic/koine, with-accusative→με αιτιατική, etc. — all keys
  lowercase to match `lookup`). **Found a real leak:** the search-results
  `explanation` was rendered straight from the backend, which embeds raw English
  tags ("…(genitive, plural)"). `ResultCard` now rebuilds the explanation
  client-side from `matched_surface`+`lemma`+`features` via `gramEl` (keeps the
  DB/API English; presentation stays Greek). Verified zero English in rendered
  search/word pages.
- **Κλίση revamp — proper Greek paradigm structure** (researched against
  Βικιλεξικό + school grammars; sources logged below). Verbs now render per-voice
  grids (Ενεργητική/Παθητική) with a **two-tier banded header** = aspect band
  (Εξακολουθητικοί / Συνοπτικοί / Προστακτική) over tense columns
  (Ενεστώτας, Παρατατικός, Εξακ. Μέλλοντας | Αόριστος, Συνοπτ. Μέλλοντας,
  Υποτακτική (να/θα), Προστακτική), rows = person×number.
  - GOTCHA fixed: en-wiktionary tags Παρατατικός as `imperfect` (NOT `past`)
    +`imperfective`, while Αόριστος is `past`+`perfective` — the old matcher
    required `past` so Παρατατικός silently vanished. Matcher now accepts
    `imperfect`.
  - Periphrastic **futures** (θα …, tagged `future`+aspect, carry person) are now
    grid columns instead of leftovers.
  - New **"Μετοχές & απαρέμφατο"** box (participles/infinitives split out of the
    catch-all via a `nonFinite` bucket in `buildInflection`).
  - **Headword seeding:** Wiktionary form tables omit the lemma's own base form,
    so the nominative-singular / present·1sg·active cell was blank (e.g. άνθρωπος).
    `buildInflection(pos, forms, lemma)` now injects a synthetic headword form
    (deduped by text). Gender is only tagged on the seeded headword when the real
    forms are gendered (adjectives) — otherwise it would split a single-gender
    noun's paradigm into two grids.
  - Nouns: 4 cases (Ονομαστική/Γενική/Αιτιατική/Κλητική — **no δοτική** in Modern
    Greek; dative row only appears if Katharevousa data carries it) × Ενικός/
    Πληθυντικός, split by gender when tagged. `Grid.columns` is now
    `GridColumn[]` ({label, group}); `InflectionTables` renders the colspan band
    row via `bandSpans()` (skipped when all groups empty, i.e. nominal grids).
  - Verified live on /word/υπολογίζω (full active+passive paradigm, α΄ ενικ. row =
    υπολογίζω/υπολόγιζα/θα υπολογίζω/—/υπολόγισα/θα υπολογίσω/υπολογίσω/—) and
    /word/άνθρωπος (Ονομ. ενικ. = άνθρωπος). Build clean; 19 tests green.
  - Grammar sources: users.sch.gr (klisi-rimatos-NE, xronoi-rim-NE),
    el.wiktionary.org (γράφω conjugation, άνθρωπος declension), Helinika tenses.

## Done this session (2026-05-31, cont. 3)
- **Clickable local launcher.** `scripts/start-lexorama.ps1` (+ `.bat` wrapper)
  starts API on :8011 (full DB via `LEXORAMA_DB`, `PYTHONIOENCODING=utf-8`, NO
  `--reload`) and web on :5180, skipping any port already listening
  (`Get-NetTCPConnection`), waits for the web port, then opens the browser.
  Desktop shortcut at `C:\Users\vmnik\OneDrive\Desktop\Lexorama.lnk` → the `.bat`
  (ASCII filename — Greek "Λεξόραμα.lnk" failed through the OneDrive path).
- **Glossary + architecture page** (`/about`, `AboutPage.tsx`). Greek glossary
  (Βασικές έννοιες / Ονόματα / Ρήματα / Σχέσεις & ιστορία) + 4 architecture
  principle cards ("Η ΤΝ εξηγεί· οι πηγές ορίζουν" etc.). Routed in `App.tsx`;
  Footer links it as "Γλωσσάρι & σχεδιασμός" next to "Πηγές & άδειες".
- **Etymology — end-to-end (NEEDS RE-INGEST to populate).** New schema tables
  `etymology` (prose, one row/lemma) + `etymons` (typed origins). Both are
  `CREATE IF NOT EXISTS` (additive — the existing full DB just gains empty tables
  until re-ingested).
  - `ingest_kaikki.py`: `extract_etymology()` reads `etymology_text` (prose) and
    `etymology_templates`, mapping inh/inh+→inherited, der/der+/uder→derived,
    bor/bor+/lbor/slbor→borrowed, cal/calque/clq→calque, cog/cogn→cognate.
    Arg layout: cognate = {1:lang,2:term}; all others = {2:src-lang,3:term}.
    Inline `{{m}}`/`{{l}}` mentions are intentionally dropped. `store_etymology()`
    is idempotent and el-preferred (el overwrites en; en never overrides el).
  - API: `/api/word` now returns per-entry `etymology:{text,source}` + `etymons:
    [{relation,lang,term,source}]`; `/api/word/{lemma}/graph` appends etymon
    edges (cross-language ancestors as unresolved square nodes tagged with lang).
  - Frontend: `labels.ts` adds `etyRelEl` (κληρονομήθηκε από / δάνειο από / …) and
    `langEl` (grc→αρχαία ελληνικά, ine-pro→πρωτοϊνδοευρωπαϊκή, gkm→μεσαιωνική, …);
    `WordPage` renders an **Ετυμολογία** card (prose + typed origin list with
    source-language + provenance badge); `RelationGraph` colours etymology edges
    in earthy tones, draws etymon nodes as squares, and shows a second
    "Ετυμολογία:" legend row only when such edges exist.
  - Verified: parser smoke test (synthetic entry) — ignores `{{m}}`, captures
    inherited/cognate, idempotent, en-no-override-el. `npm run build` clean.
  - **el dump has NO `etymology_templates`** — only prose `etymology_text`. Added
    `parse_el_etymology_prose()`: deterministic Greek-prose parser that extracts the
    immediate ancestor from "headword < (marker) LANGUAGE term < …" (Greek
    language-name → code map `_EL_LANGS`; relation from marker, defaulting to
    inherited for older-Greek/PIE stages, borrowed for foreign). ~34% of el prose
    entries (≈45% of lemma-matched ones) yield a clean etymon; the rest are internal
    compounds with no source language (correctly skipped — prose still shown).
    `extract_etymology` uses templates when present (en), else prose (el).
  - **`--etymology-only` ingest mode** (`ingest_etymology_only`): streams a dump and
    updates ONLY etymology/etymons for already-existing lemmas — NO lemma/sense/
    form/relation inserts. This is the safe, idempotent, re-runnable way to add
    etymology to a populated DB. (A normal re-ingest would DUPLICATE senses/forms/
    relations — only lemmas are deduped.) Validated: 40k-line el pass → 21,841
    matched / 0 unmatched / 9,819 etymons; χρώμα→grc χρῶμα, μπιζέλι→it piselli.
  - **API self-heals** a pre-etymology DB (`db()` runs CREATE IF NOT EXISTS for
    etymology/etymons) so /api/word never 500s before the etymology pass.
  - **TODO for user — one command** (en etymons already present from full ingest;
    el needs the prose pass). Close the API window first, then:
    `python pipelines\ingest\ingest_kaikki.py --input data\raw\el-extract.jsonl
    --source el-wiktionary --db data\db\lexorama.sqlite --etymology-only` then
    relaunch. No search_index rebuild needed.
- **IPA pronunciation — end-to-end (NEEDS the `--ipa-only` pass to populate).**
  Word-level roadmap #1. New schema table `pronunciations` (lemma_id, ipa, source,
  seq; PK `(lemma_id, ipa)`) — `CREATE IF NOT EXISTS`, additive. A lemma may carry
  multiple readings (e.g. ήλιο /ˈi.li.o/ ~ /ˈi.ʎo/).
  - `ingest_kaikki.py`: `extract_pronunciations()` pulls `sounds[].ipa` (audio is
    link-out only), unescapes, strips wrapping `/[]`, de-dupes preserving order.
    `store_pronunciations()` is idempotent + el-preferred (el pass replaces a lemma's
    readings; en only fills lemmas with none). `--ipa-only` mode
    (`ingest_pronunciation_only`) mirrors `--etymology-only`: streams a dump and
    updates ONLY `pronunciations` for existing lemmas — no lemma/sense/form/relation
    inserts, safe to re-run.
  - API: `db()` self-heals (CREATE IF NOT EXISTS `pronunciations`); `/api/word`
    returns per-entry `pronunciations:[{ipa,source}]`.
  - Frontend: `types.ts` adds `Pronunciation`; `WordPage` renders the IPA in
    monospace next to the headword as `/ˈxɾo.ma/` (joined by spaces if multiple).
  - Verified: 20k-line el `--ipa-only` pass → 3,473 matched / 0 unmatched / 3,552
    ipas; DB + `word()` route return χρώμα /ˈxɾo.ma/, γένος /ˈʝe.nos/, λέξη /ˈle.ksi/.
    `npm run build` clean. ~12% of el lemmas carry IPA in the sampled slice.
  - **TODO for user — two commands** (el then en fallback). Close the API window
    first, then:
    `python pipelines\ingest\ingest_kaikki.py --input data\raw\el-extract.jsonl --source el-wiktionary --db data\db\lexorama.sqlite --ipa-only`
    then optionally
    `python pipelines\ingest\ingest_kaikki.py --input data\raw\en-extract.jsonl --source en-wiktionary --db data\db\lexorama.sqlite --ipa-only`
    then relaunch. No search_index rebuild needed. (Only the first 20k lines are
    populated so far from the validation pass.)
- **Word family + descendants — end-to-end (descendants NEED a `--descendants-only`
  pass; word family needs NO re-ingest).** Word-level roadmap #2.
  - **Word family** (no new data): the typed lexical relations already in the
    `relations` table (synonym/antonym/derived/related/…) are now surfaced as a
    readable **Οικογένεια λέξεων** card on the word page — grouped by relation,
    rendered as chips (resolved targets link to their word page, unresolved are
    plain text), capped at 24/group with a "+N ακόμη" note. `/api/word` builds a
    per-entry `family:[{relation,terms:[{term,resolved,source}]}]` (de-duped,
    self-reference filtered). Same edges the graph draws, but scannable.
  - **Descendants** (new data): cross-language words formed FROM a Greek lemma —
    the forward mirror of etymology (e.g. Ελλάδα → English "Ellada", Russian
    "Элλάδα"). New `descendants` table (lemma_id, relation, lang_code, lang_name,
    term, roman, source, seq). `extract_descendants()` reads en-wiktionary's
    `descendants` field (raw_tags → relation, mostly "borrowed"); `--descendants-only`
    mode (`ingest_descendants_only`) mirrors the etymology/IPA passes (no row
    duplication). API self-heals the table + returns per-entry
    `descendants:[{relation,lang,lang_name,term,roman,source}]`; `WordPage` renders
    an **Απόγονοι σε άλλες γλώσσες** card. Frontend types: `FamilyGroup`,
    `FamilyTerm`, `Descendant`.
  - Verified: 85k-line en `--descendants-only` pass → 378 matched / 0 unmatched /
    847 descendants; `word()` route returns Ελλάδα → en Ellada / ru Элλάδα,
    μοναστήρι → ro mânăstire, and family groups for λέξη/μοναστήρι. `npm run build`
    clean. Descendants are sparse (~379 lemmas in the en dump) but unique.
  - **TODO for user — one command** (en only; close the API window first):
    `python pipelines\ingest\ingest_kaikki.py --input data\raw\en-extract.jsonl --source en-wiktionary --db data\db\lexorama.sqlite --descendants-only`
    then relaunch. No search_index rebuild. (Only first 85k lines populated so far.)
- **Usage labels as chips — end-to-end (domains NEED a `--sense-tags-only` pass;
  register chips work on existing data).** Word-level roadmap #3.
  - **Classifier** (`labels.ts` `classifyTags(tags)`): splits a sense's flat tag
    array into three buckets — **usage** (register/period/dialect: figuratively,
    formal, familiar, slang, vulgar, archaic, Katharevousa, Koine, Cypriot, …),
    **domain** (subject field), and a curated few **grammar** tags (transitive,
    intransitive, countable, …). Pure inflectional tags (case/number/gender/person)
    are intentionally dropped — they live in the Κλίση tables, not on a sense.
    New maps `DOMAIN_EL` (medicine→ιατρική, law→νομική, computing→πληροφορική, …),
    `USAGE_KEYS`/`USEFUL_GRAM_KEYS` sets, `DIALECT_USAGE_EL`; helpers `usageEl`,
    `domainEl`. `WordPage` `<SenseLabels>` renders usage = amber chips, domain =
    indigo chips, grammar = muted chips.
  - **Domain capture** (new data): Wiktionary keeps subject domains in a separate
    `topics` list (not previously ingested). New `sense_tags(sense)` helper merges
    `tags + topics` (de-duped) — used by the full ingest AND by a new
    **`--sense-tags-only`** pass (`ingest_sense_tags_only`) that refreshes the
    `tags` column of EXISTING senses in place by (lemma_id, sense_index, source),
    so no re-ingest / duplication. Register labels were already in `tags`, so the
    amber chips light up with no pass; domains need the pass.
  - Verified: 250k-line el `--sense-tags-only` pass → 63,635 matched / 0 unmatched /
    95,652 senses updated; DB now shows ορθοδοντική/τραύμα→["medicine"], βάση→["law"],
    λέξη→["computing"], ορχήστρα→["music"], plus register (figuratively/familiar/
    slang) on λέξη/δόντι/λάδι. `npm run build` clean.
  - **TODO for user — two commands** (el then en; close the API window first):
    `python pipelines\ingest\ingest_kaikki.py --input data\raw\el-extract.jsonl --source el-wiktionary --db data\db\lexorama.sqlite --sense-tags-only`
    then
    `python pipelines\ingest\ingest_kaikki.py --input data\raw\en-extract.jsonl --source en-wiktionary --db data\db\lexorama.sqlite --sense-tags-only`
    then relaunch. No search_index rebuild. (Only first 250k el lines populated so far.)
- **Audio pronunciation (roadmap #4) — SKIPPED for now** (user call: low coverage,
  low priority). Audio in the dumps is link-out only anyway; revisit later as a
  speaker icon linking to Wiktionary/Forvo.
- **Corpus frequency — end-to-end (NEEDS a frequency list file + the new script).**
  Word-level roadmap #5. Wiktionary has no frequency, so it's layered from an
  external word list.
  - New table `frequency` (lemma_id PK, count, rank, zipf, band, source). New
    standalone script **`pipelines/ingest/ingest_frequency.py`**: reads a plain
    "word<space>count" file, resolves each surface through `search_index` (so
    inflected forms count toward their lemma), SUMS counts per lemma, computes
    Zipf = log10(count per billion) and a coarse band (very_common ≥5, common ≥4,
    moderate ≥3, uncommon ≥2, else rare), assigns a dense rank, and writes rows.
    Idempotent (clears its `--source` first). Attribution row added to SOURCE_META
    (`opensubtitles-freq`, CC BY-SA 4.0, hermitdave/FrequencyWords / OpenSubtitles).
  - API: `db()` self-heals the table; `/api/word` returns per-entry
    `frequency:{count,rank,zipf,band,source}|null`.
  - Frontend: `Frequency` type; `labels.ts` `FREQ_BAND_EL`/`FREQ_BAND_LEVEL` +
    `freqBandEl`/`freqBandLevel`; `WordPage` `<FrequencyMeter>` shows a 5-segment
    emerald bar + Greek band label next to the headword (Zipf + source in tooltip).
  - Verified with a synthetic list (source `test-freq`, since removed): all surfaces
    matched, aggregation through search_index credits homograph lemmas, API returns
    count/rank/zipf/band; χρώμα→very_common, ορθοδοντική→moderate. `npm run build`
    clean. (Synthetic Zipf was inflated by the toy corpus total; real list gives the
    proper 1–7 scale.)
  - **DONE (user ran it).** Download (PowerShell `curl` is Invoke-WebRequest, no `-L`;
    use `curl.exe -L -o ...` OR `Invoke-WebRequest -Uri "<url>" -OutFile data\raw\el_freq.txt`),
    then `python pipelines\ingest\ingest_frequency.py --freq-file data\raw\el_freq.txt --db data\db\lexorama.sqlite`.
    Result: 50,000 rows / 251.8M-word corpus, 43,180 surfaces matched (86%),
    25,838 lemmas scored; bands very_common 3,086 / common 7,531 / moderate 12,091 /
    uncommon 3,130 / rare 0 (the top-50k list bottoms out ~Zipf 2.5, so nothing is
    "rare"; the ~420k lemmas not in the corpus show no meter — correct). Verified:
    είμαι Zipf 8.1 (rank 17, aggregates all conjugated forms) > και 7.41; νερό 5.64,
    χρώμα 5.2, θάλασσα 5.08 very_common; φιλοσοφία 4.18 common; ορθοδοντική no-freq.
- **Collocations — end-to-end (NEEDS a Leipzig corpus + the new script).**
  Word-level roadmap #6. Wiktionary has no collocation data, so it's layered from
  an external corpus: the **Wortschatz Leipzig** "Corpora Collection" for Modern
  Greek, which ships sentence co-occurrence stats.
  - New table `collocations` (id, lemma_id, collocate, collocate_lemma_id, score,
    source, seq) — `CREATE IF NOT EXISTS`, additive. New standalone script
    **`pipelines/ingest/ingest_collocations.py`**: parses Leipzig `*-words.txt`
    (`id<TAB>word<TAB>freq`) + `*-co_s.txt` (`w1<TAB>w2<TAB>freq<TAB>significance`),
    builds per-word collocate lists from BOTH columns (pairs stored once,
    unordered), resolves words to lemmas via `search_index`, keeps the top
    `--top-n` (default 12) collocates per lemma by significance (log-likelihood),
    and resolves each collocate to a lemma_id for link-out when known. Drops tokens
    <3 chars and self-collocations. Idempotent (clears its `--source` first).
    Attribution row added to SOURCE_META (`leipzig-coocc`, CC BY 4.0).
  - API: `db()` self-heals the table; `/api/word` returns per-entry
    `collocations:[{collocate,collocate_lemma_id,score,source}]` (ordered by seq).
  - Frontend: `Collocation` type; `WordPage` `<EntryCollocations>` renders a
    **Τυπικές συνάψεις** card of chips (teal + clickable when the collocate is a
    known lemma, muted otherwise) in the Ορισμοί stack after Οικογένεια λέξεων.
    Distinct from the curated lexical family: these are emergent corpus usage.
  - Verified with a synthetic two-file fixture (source `leipzig-test`, since
    removed): 7 words all matched, ranked by score desc, links resolved
    (νερό→πίνω/ποτήρι/θάλασσα), self excluded, "το" (<3 chars) dropped, homograph
    lemmas (νερό/Νέρο) both credited. `npm run build` clean. DB left clean.
  - **DONE (ran on `ell_news_2020_1M`).** Download a Greek corpus from
    https://downloads.wortschatz-leipzig.de/corpora/ell_news_2020_1M.tar.gz (or pick
    one at the Leipzig portal), `tar -xzf` it, then run the ingest pointing at the
    `<archive>\<archive>-words.txt` + `-co_s.txt` files INSIDE the unpacked folder.
    Result: 471,714 corpus words, 72,058 matched to lemmas, **37,662 lemmas scored
    / 294,045 collocation rows, 88% of collocates link to a word page.** Verified:
    νερό→σαπούνι/ζεστό/κρύο/ποτήρι/πόσιμο; αυτοκίνητο→οδηγός/ηλεκτρικό/σταθμευμένο/
    συγκρούστηκε; βιβλίο→τίτλο/εκδόσεις/συγγραφέας/μυθιστόρημα.
  - **Lessons baked into the script (don't regress):**
    - The `-co_s.txt` is HUGE (1M corpus = 4.9M pairs / 88 MB). The script **streams**
      it and only keeps collocates for words that resolve to a lemma — memory is
      bounded by the lexicon, not the corpus. (v1 loaded all pairs in both
      directions ≈2 GB and got OOM-killed mid-run, printing only its header.)
    - **CLOSE THE API FIRST.** The launcher's API (PID on :8011) holds the DB; a
      write-ingest will block/fail while it's up. (Same rule as the `--*-only` passes.)
    - **Stopword filter + dedupe** are essential for chip quality: Greek function
      words (articles/preps/conjunctions/pronouns/auxiliaries + indefinite article,
      set `STOPWORDS` in the script) have huge raw log-likelihood and otherwise
      dominate the top-12; and collocates are deduped by RESOLVED lemma (so
      inflected variants of one target collapse to a single chip, highest score
      kept) with the headword's own forms excluded. Slice to top_n AFTER dedupe.
- **Launcher encoding bug fixed.** `start-lexorama.ps1` was saved BOM-less with Greek
  text + em-dashes; PowerShell 5.1 reads BOM-less .ps1 as cp1252 → mangled bytes →
  parse error → the double-clicked window died instantly. Rewrote the script
  ASCII-only (and `$apiCmd` on one line); parses clean, 0 non-ASCII bytes. Shortcut
  now launches both servers + browser. (NOTE: uvicorn binds 127.0.0.1 (IPv4); test
  with http://127.0.0.1:8011, not `localhost`, which may resolve to ::1.)
- **Usage-chip QA (roadmap #3 polish).** Surveyed the live DB's actual sense tags
  (`SELECT tags FROM senses`) against `labels.ts` classification and fixed silent
  drops/English-leakage:
  - **Capitalized DOMAIN_EL keys never matched.** `classifyTags`/`domainEl` lowercase
    the tag before lookup, but `Christianity`/`Greek` were stored capitalized →
    never hit. Lowercased to `christianity`/`greek`. (`Katharevousa` was fine — its
    key was already lowercase, and the tag lowercases to match.)
  - **High-frequency subject tags were being dropped** (not in DOMAIN_EL, so
    `classifyTags` discarded them): added `sciences`, `natural-sciences`,
    `physical-sciences`, `human-sciences`, `social-sciences`, `engineering`,
    `government`, `lifestyle` (each 480–2,550 occurrences in the DB).
  - **Two USAGE_KEYS had no Greek display** → rendered raw English: added
    `literary`→λόγιο, `disapproving`→αποδοκιμαστικό to DIALECT_USAGE_EL.
  - `npm run build` clean; live `/api/word` smoke test returns the new
    `collocations` field (count 0 until Leipzig ingest) with freq/IPA/family intact.

## Done — backlog Phase 1 (#28–#31)
*(recorded retroactively — these shipped but were missing from HANDOFF's Done log)*
- **#28 Greeklish vowel-expansion — DONE.** `normalize_greek.greeklish_candidates(text,
  max_candidates=64)` enumerates plausible Greek transliterations (digraph + vowel
  alternatives, likelihood-ordered, first = `greeklish_to_greek`). `main.py` search
  (`resolve`/index probe) tries each candidate and ranks hits by lemma frequency. No
  longer one lossy transliteration.
- **#29 Saved words + recent-search history — DONE.** `apps/web/src/hooks/useUserData.ts`:
  client-only localStorage (`lexorama.saved.v1` cap 300, `lexorama.recent.v1` cap 12),
  cross-tab sync via the `storage` event, `useSyncExternalStore`. Privacy story intact
  (stays on device). Wired into `SearchPage`.
- **#30 Audio pronunciation — DONE (link-out).** IPA shown; audio is link-out only
  (dump coverage is sparse), per the deliberate user call noted above.
- **#31 Dispersion-aware keyness — DONE.** `main.py` /explore/compare keyness uses Gries'
  Deviation of Proportions (DP = ½·Σ|vᵢ−sᵢ| over corpus years), gating out terms whose
  mass is concentrated in one year (DP ≤ max_dp) so a one-off spike can't masquerade as
  distinctive vocabulary. `dp_parliament` / `dp_news` surfaced on each `KeynessItem`.

## Done this session (2026-06-02) — backlog Phase 2 (#32) + Phase 3 (#33)
- **#32 Paradigm engine — DONE end-to-end.** `pipelines/ingest/paradigm_engine.py`
  generates κλίση/conjugation; `validate_paradigms.py` gates each class at ≥0.97
  precision vs real Wiktionary forms; `backfill_paradigms.py` inserts ONLY missing
  cells tagged `source='generated'` (idempotent: deletes prior generated rows first).
  - 13 classes all clear the bar (adj:-ος 0.994, noun:-α 0.998 / -η 0.994 / -ι 0.994
    / -μα 0.996 / -ο 0.972 / -ος 0.981, verb present 0.979, …). **170,749 cells**
    backfilled; search index rebuilt → 3,663,525 rows.
  - Morphology decisions baked in: proparoxytone **genitive shift is lexical**
    (άνθρωπος→ανθρώπου vs γάιδαρος/νούμερο keep) → genitive cells DROPPED for -ος/-ο
    rather than guess; -μα neuters use oblique stem +τ; **hiatus_ambiguous() guard**
    (γάιδαρος: stripping tonos off άι spuriously forms digraph αι) returns [];
    verbs limited to conjugation A (-ω). The miss tail is genuine irregular subclasses.
  - Frontend: generated cells render with a dotted-underline + `*` superscript and a
    Greek footnote ("αλγοριθμικά παραγόμενος τύπος… όχι από πηγή") — never passed off
    as sourced. `inflection.ts` tracks per-cell source set; `isGen` = all sources
    'generated'. tsc clean.
- **#33 Graph densification (WordNet/OMW) — DONE.** `pipelines/ingest/ingest_wordnet.py`
  (`source='omw-el'`) uses `wn.Wordnet("omw-el:1.4", expand="omw-en:1.4")`: omw-el gives
  Greek lemma→synset membership, the Princeton omw-en *expand* structure gives the is-a
  relations Wiktionary lacked (was ~130 hypernym/hyponym edges total).
  - **40,413 edges** over 10,140 matched headwords: 15,246 hypernym, 15,136 hyponym,
    10,031 synonym. Edge contract: POS-matched, linked-only (both endpoints existing
    single-word lemmas — no dangling text nodes), idempotent (DELETE WHERE source first),
    provenance-tagged.
  - Graph endpoint `/api/word/{lemma}/graph` reworked: CASE-based ORDER BY ranks typed
    edges (synonym/antonym/hypernym/hyponym/derived) ahead of the ~186k `related`
    catch-all, prefers resolved targets, LIMIT 60, dedups parallel (target,type) edges.
    Verified on αυτοκίνητο → hypernym περιεχόμενο + hyponyms ταξί/τζιπ/ασθενοφόρο/σαράβαλο,
    all `source_name='omw-el'`.
  - Frontend already supports it: `labels.ts` υπερώνυμο/υπώνυμο; `RelationGraph.tsx`
    colors (amber hypernym / cyan hyponym) + legend + tooltip showing `· omw-el`.
  - Provenance + legal: added `omw-el` to `SOURCE_META` (Apache-2.0 / Princeton WordNet
    3.0); ingest now calls `record_attribution` → appears in `/api/attributions`, the
    footer, and `/licensing`. `docs/data_sources.md` + `docs/licensing.md` updated.
- **#34 Multi-hop etymology chains + cognate cross-links — DONE.**
  - **Root cause of flat etymology:** `parse_el_etymology_prose` only ever emitted
    the IMMEDIATE ancestor, so ~97% of lemmas had a single etymon. Rewrote it to walk
    the WHOLE " < " prose chain, emitting one typed `(relation, lang, term, seq)` per
    step that names a recognised language; skips internal/redirect/"λείπει" steps and
    connector words ("ρίζα", "λέξη"). 5 unit tests in `tests/test_etymology_chain.py`.
  - **No 1.4GB re-stream:** `pipelines/ingest/reparse_etymology.py` re-applies the new
    parser to prose ALREADY in the `etymology` table, idempotent, faithful to
    `store_etymology` precedence (el overrides en). el etymons 33,069 → **52,928**;
    lemmas with a chain → **38,806** (10,731 genuine multi-hop ≥2); 765 stale cleaned.
  - **Graph = lineage path:** word_graph etymon edges now CHAIN by seq
    (headword → grc-koi → la → ine-pro) instead of a flat star. `EtymologyTimeline`
    (already built) now lights up for the multi-hop lemmas.
  - **Cognate cross-links:** word payload gains `cognates` — other MG lemmas sharing
    an etymological ancestor, ranked by ancestor specificity (mega PIE clusters >60
    skipped), shown grouped by shared root ("κοινή ρίζα: grc χρῶμα") in new
    `EntryCognates` panel on WordPage. New index `idx_etymons_ancestor (lang_code,term)`.
  - 19 backend + 5 new etymology tests green; web tsc clean.
- **#35 Trajectory / change-point drift — DONE.**
  - **Root limitation fixed:** drift was endpoints-only (first↔last), so a word that
    drifted then reverted looked stable. `ingest_diachronic.py` now aligns EVERY dense
    slice (Procrustes) to the reference = first dense slice and stores per-slice cosine
    `distance_from_ref` in a new `diachronic_trajectory` table. Re-ran both axes from
    materialized slices (`--skip-materialize`): **parliament 181,083** traj rows (29
    dense slices, 1990–2020), **news 118,084** (11 slices, 2011–2024).
  - **Change-point = steepest single step AMONG comparison slices**, stored on
    `diachronic_drift.change_point_year`. We SKIP the reference→first step: distance
    jumps 0→~0.3+ from independent-model variance alone, so unskipped it always wins and
    every word's change-point collapses to its 2nd slice (observed + fixed). After the
    fix, change-points spread across years (parliament 1992–2015, news peaks 2019).
    Pure `change_point_year(series)` extracted → unit-tested in `tests/test_change_point.py`.
  - **Recompute trick:** after changing the heuristic I recomputed `change_point_year`
    in-place from the stored `diachronic_trajectory` (a ~1s Python pass) instead of
    re-running the ~12-min word2vec ingest. Same logic, no retrain.
  - **API + UI:** `/api/word/{lemma}/diachronic` series gains `trajectory[]` +
    `drift.change_point_year`. `DiachronicPanel` draws a per-corpus `TrajectoryChart`
    (distance-from-reference line, change-point ringed) above the drift badges; badge
    appends "· καμπή ~YYYY". Verified live: κρίση parl cp=2004/news cp=2016,
    δίκτυο cp=2020/2019. Methodology page §drift + limitations updated.
  - 24 backend + 4 new change-point tests green (28 total); web tsc clean.
- **#36 Confidence intervals / significance on drift & trends — DONE.**
  - **Drift CIs by retraining anchors (user-chosen method).** New
    `pipelines/ingest/bootstrap_drift.py`: resamples the two anchor slices' sentences
    WITH REPLACEMENT K=12× (capped at `--cap 250000` so news' 1M-line slice stays
    tractable; a smaller draw only WIDENS the CI = conservative), retrains word2vec on
    each, Procrustes-aligns each last_k→first_k → a per-lemma drift distribution →
    **95% CI** (2.5/97.5 pct) stored on `diachronic_drift.drift_ci_lo/drift_ci_hi`.
  - **Significance vs the word's own noise (Dubossarsky no-change control).** Reuses the
    K first-slice models as a null: distance between two bootstrap models of the SAME
    first slice (first_i↔first_j) is pure estimation noise (no time elapsed) — no extra
    training. A lemma is `drift_significant=1` when its real-drift CI lower bound clears
    the control-noise CI upper bound (`real_pct2.5 > ctrl_pct97.5`).
  - **Ran both axes (API stopped for the write):** parliament K=12 ~7.7 min →
    **5,519 lemmas with CIs, 3,589 significant**; news K=12 --cap 250000 ~60 min →
    **8,713 with CIs, 4,550 significant**. Idempotent UPDATE-in-place (only rows already
    in `diachronic_drift`); doesn't retrain the whole trajectory, just the 2 anchors.
  - **Trend significance was already analytical + cheap** (no retraining): `/explore/trends`
    computes the OLS slope's two-sided t-test p-value from the same aggregate sums it
    already had (`p_value`, `significant = p<0.05`); ExplorePage marks significant slopes
    with ✸. (Confirmed present from #22-era work — kept.)
  - **API + UI:** `word_diachronic` drift dict gains `drift_ci_lo/drift_ci_hi/drift_significant`
    (bool|null); `DiachronicPanel` DriftBadge renders `±95% [lo–hi]` + a
    `σημαντική`/`μη σημαντική` chip. Methodology §drift gained a bootstrap-CI paragraph;
    limits bullet corrected (drift significance now estimated, change-point significance
    not yet). Verified live: κρίση parl drift 0.277 CI [0.275–0.351] significant,
    news 0.243 CI [0.285–0.365] significant. web tsc clean.
- **#37 Pooled / larger slice training — DONE.**
  - **Why:** per-year word2vec models are thin in low-volume years, so rare-word
    vectors stay noisy even past the frequency gate. Fix = standard diachronic binning
    (Hamilton 2016 / Kim 2014): each slice now trains on a **±2-year band** of adjacent
    same-corpus years, still LABELED by its centre year (drift/trajectory semantics and
    the one-corpus-per-axis rule unchanged) — it just sees ~5× the sentences.
  - **Pipeline:** `ingest_diachronic.py` gains `_pool_members(center, years, window)` +
    `_pooled_to_tempfile(paths, cap, tmp_dir)` (concatenates the band into a temp train
    file, uniform-RESERVOIR-capped at `--pool-cap` 500k so already-dense news years stay
    tractable — the cap only ever bites years that were stable without pooling). New CLI:
    `--pool-window` (0=off, default), `--pool-cap`, `--seed`. `bootstrap_drift.py` gains a
    matching `--pool-window`/`--pool-cap` (via `_read_anchor_lines`, reservoir-capped) so
    the CI is bootstrapped on the SAME pooled estimator as the point estimate.
  - **Re-ran BOTH axes at ±2 (API stopped), then re-bootstrapped both:**
    - parliament ingest: vocab ~3× (e.g. 2018 59,029 vs ~22k); anchor RESCUED 1990→**1989**
      (pooled 1989–1991 now dense, vocab 36,667); drift_rows 5,680→**9,259**, trajectory
      181,083→**322,029**. Pooled bootstrap K=12 (~35 min): **9,003 CIs, 5,494 significant**.
    - news ingest: uniform ~45k vocab/slice; drift_rows 11,088→**13,140**, trajectory
      118,084→**152,618**. Pooled bootstrap K=12 cap 250k: **9,225 CIs, 3,752 significant**.
  - **Verified live:** κρίση parl drift 0.282 CI [0.227–0.371] significant cp 2013 (31
    traj pts); news 0.237 CI [0.217–0.276] significant cp 2016. The point estimate now
    falls INSIDE its CI (both use the pooled estimator) — was occasionally outside before.
  - 6 new tests in `tests/test_pooling.py` (34 total green); web tsc clean. Methodology
    §freqgate gained a pooling paragraph; limits bullet corrected (pooling reduces—not
    eliminates—rare-word noise and slightly blurs temporal resolution).
- **#38 Supervised domain attribution (§ ανά πεδίο) — DONE.**
  - **Why:** the "μετατοπίσεις ανά πεδίο" lists assigned a lemma to a subject field
    purely by intersecting `senses.tags` with a fixed field list — defensible only for
    the ~15k lemmas Wiktionary happens to topic-tag; every other content word got no
    field. Backlog asked for a "trained classifier … to make domain attribution
    defensible." Replaced the lexicon lookup with distant supervision.
  - **Pipeline:** new `pipelines/ingest/classify_domains.py`. Pools ALL 42 diachronic
    slices (both corpora) into ONE word2vec embedding — domain is a STATIC lexical
    property, so pooling every year/corpus for coverage is correct here (the opposite
    of drift work, where slices must stay separate). **skip-gram, min_count=3,
    vector_size=150** (skip-gram markedly beat CBOW on the rare technical vocab: held-out
    acc 0.478→**0.560**, macro-F1 0.383→**0.463**). Gold labels = the single-field-tagged
    lemmas (clean supervision); X = L2-normalized lemma vector, y = field; **class-balanced
    multinomial logistic regression** (fields span ~50 economics → ~3000 medicine).
    Reports held-out accuracy/macro-F1 on a stratified split, refits on all gold, predicts
    a top field + softmax confidence for every CONTENT lemma (noun/adj/verb) with a vector
    and NO gold tag. CLI: `--sg`/`--vector-size`/`--min-count`/`--epochs`/`--seed`.
  - **Schema:** new `lemma_domain_pred (lemma_id, domain, score, rank, source)` + indexes.
    Gold tags written verbatim (`source='wiktionary-tag'`, score 1.0, incl. multi-tag
    lemmas) and stay AUTHORITATIVE; classifier rows (`source='classifier'`, score=confidence)
    only ADD coverage for untagged lemmas, stored above STORE_FLOOR 0.30. "Sources define,
    AI explains" preserved end to end.
  - **API:** `db()` has a `CREATE TABLE IF NOT EXISTS lemma_domain_pred` guard (graceful
    pre-run). `_lemma_domains` now returns lemma_id → {domain: (source, score)} from the
    table — gold always kept, classifier gated at `_DOMAIN_PRED_GATE=0.55` (display gate,
    tunable without re-ingest) — with a **fallback to the legacy senses.tags heuristic if
    the table is empty**. `explore_by_field` surfaces `domain_source`/`domain_score` per
    mover + `inferred_share` per field.
  - **Frontend:** `FieldMover` type (+`inferred_share`); ExplorePage marks classifier-
    inferred movers/fields with a `~` badge + confidence tooltip; updated blurb.
    Methodology gained a "Απόδοση θεματικού πεδίου (επιβλεπόμενη ταξινόμηση)" section;
    the loose-domain limitation bullet rewritten.
  - **Ran (API stopped, skip-gram):** embedding vocab **532,261**; training examples
    **4,983**/18 fields; **gold_rows 17,201**, **classifier_rows 17,699** (≥0.55 gate:
    **5,601**; ≥0.70: 2,699). Verified live: parliament+news by-field return all 18 fields
    with mixed gold/inferred movers (e.g. αυτόματο→technology, κινητό→computing 0.77,
    αυγό→biology, λατινικά→linguistics; gold βάρκα→nautical, θείο→chemistry stay clean).
  - 6 new tests in `tests/test_domains.py` (`SliceReader` + `_gold_domains`); **40 total
    green**; web tsc clean.
- **#39 Bilingual el↔en mode — DONE (scope: English glosses + cross-language search; UI stays Greek).**
  - **Why:** the en-Wiktionary edition was already ingested (45,741 en senses on 31,817
    lemmas) but unused — word pages hid English glosses (fallback-only) and you couldn't
    look a Greek word up by its English meaning. Chosen scope (via AskUserQuestion):
    English glosses on word pages + en→el search; a full UI language toggle was NOT done.
  - **Cross-language search (en→el):** new `pipelines/ingest/build_gloss_index.py` extracts
    the clean LEADING headword phrase(s) from each English gloss (drops parentheticals,
    splits on ;/,/ , strips leading articles, skips cross-reference/"form of" glosses,
    accepts only short ASCII 1–3-word phrases so Greek never leaks in) → `gloss_index
    (en_term, lemma_id, rank_weight, source='en-wiktionary')`, weighting a gloss's first
    clause above later ones. **Built: 58,458 rows, 34,988 distinct terms, 26,869 lemmas.**
    Precision over recall — a wrong key misroutes a searcher.
  - **API:** `db()` guards `gloss_index`. `/api/search` gains a 3rd pass (after direct +
    greeklish, since Greek stays primary): normalize the query as English (`_en_key`), look
    it up in `gloss_index`, rank by `rank_weight` then lemma frequency, emit with
    `match_type='translation'`, `via='translation'`, explanation `"eagle → αετός"`.
    Verified: eagle→αετός, bone→οστό/κόκαλο, wolf→λύκος, freedom→ελευθερία,
    love→αγαπάω/έρωτας/αγάπη, water→νερό/ύδωρ.
  - **Word page glosses:** `EntryDefinitions` now offers en glosses behind an
    "Εμφάνιση αγγλικών ορισμών (English)" toggle (collapsed by default; Greek stays
    primary; still falls back to English-as-primary when a lemma has NO Greek gloss).
  - **Frontend:** `MatchType` gains `"translation"`; `matchEl` → "μετάφραση"; ResultCard
    shows the "eagle → αετός" bridge + a sky "μέσω αγγλικών" via-badge. SearchPage
    placeholder/hint/examples now advertise English lookup (example chip "eagle").
  - 8 new tests `tests/test_gloss_index.py` (`_phrases` extraction); **48 total green**;
    web tsc clean.
- **#40 Additional corpora on their own axes — INFRASTRUCTURE DONE; data acquisition pending.**
  - **Why:** the diachronic layers carried only Parliament (1989–2020) + Leipzig
    ell_news (2011–2024). Adding a corpus was blocked by a latent conflation bug:
    `discover_leipzig_slices(root)` matched ANY `*_YYYY_*` folder, so a second Leipzig
    corpus (e.g. `ell_wikipedia_*`) dropped beside the news folders would be swept
    into the **news** axis — a cardinal-rule violation (corpora must never merge).
  - **What shipped (the multi-axis enabler, fully in-session + tested):**
    - `pipelines/ingest/corpus_sources.py`: `leipzig_source()` (prefix before the
      4-digit year), `leipzig_corpus_label()` (`ell_news`→`news`, `ell_wikipedia`→
      `wiki`, `ell-eu_web`→`web`, …; unknown → strip `ell[-_]` tag), `LEIPZIG_CORPUS_LABELS`,
      `discover_leipzig_slices(root, source=…)` (filters to ONE corpus — the cardinal-rule
      guard), and `discover_leipzig_sources(root)` (label→years overview).
    - Layer B `ingest_frequency_timeseries.py` + Layer C `ingest_diachronic.py`: new
      `--leipzig-source` flag; axis label derived from it; both **refuse to run** with
      a bare `--leipzig-dir` when the directory holds >1 corpus (forces an explicit
      axis choice). `materialize_leipzig(dir, corpus, source)` now writes to
      `data/processed/diachronic/<corpus>/`. `bootstrap_drift.py` was already
      corpus-agnostic (`--corpus`).
    - API `main.py`: `_CORPUS_ORDER` extended (`wiki`/`web`/`literature`/`mixed`); the
      diachronic + explore endpoints already `SELECT DISTINCT corpus`, so a new axis
      surfaces with zero further wiring.
    - Web: `DiachronicPanel.tsx` + `ExplorePage.tsx` gained Greek labels/colors for
      `wiki`/`web`/`literature`; the Εξερεύνηση corpus toggle is now **dynamic** —
      it discovers available axes from `/api/explore/overview` (hidden when <2 exist),
      so a freshly-ingested axis appears automatically. The two-corpus **Σύγκριση**
      quadrant stays Parliament↔news by design (it's an explicit pairwise comparison).
  - **What remains:** purely **data acquisition** — download an actual second Leipzig
    corpus (Wikipedia/web) or a literary corpus and run the scoped Layers B/C. Those
    dumps are large and MUST be fetched outside an LLM session; the exact commands are
    documented at the bottom of `pipelines/download_data.ps1`.
  - 9 new tests `tests/test_corpus_sources.py` (name parsing, label mapping, and the
    source-filtered discovery guard incl. a wiki-beside-news fixture); **57 total green**;
    web tsc clean. Verified live: real `data/raw` still resolves a single clean `news`
    axis (existing commands unchanged, no flag needed); API restarted on 8011.
- **Next in backlog: #41/#42** (P7 infra — Postgres+pg_trgm, CI/locked refresh,
  observability) — infra LAST, per the locked mandate. Feature backlog (#28–#40) is
  now code-complete (only the #40 corpus data download remains operational).

## Known gaps / next builds
- ~~**Greeklish is lossy on vowels**~~ **DONE (#28).** `normalize_greek.greeklish_candidates`
  enumerates plausible transliterations (digraph + vowel alternatives, bounded to 64,
  likelihood-ordered); `main.py` search probes each candidate and ranks hits by lemma
  frequency. `anthropon`-style vowel ambiguity now resolves.
- ~~**Paradigm engine**~~ **DONE (#32).** `paradigm_engine.py` generates rule-based
  declension/conjugation, so morphology tables are complete, not just source forms.
- ~~**Graph (M4)**~~ **DONE (#33).** WordNet/OMW typed edges (`ingest_wordnet.py`) +
  static embeddings fill sparsity; every edge typed + sourced.
- **Remaining backlog:** #36 (significance/CIs — IN PROGRESS) → #37 (pooled slice
  training) → #38 (supervised domain attribution) → #39 (bilingual el↔en) → #40 (more
  corpora); infra #41 (Postgres+pg_trgm) / #42 (CI + observability) LAST.
- **Frontend prototype complete** (Phases 1–5). Cytoscape is now code-split:
  `WordPage` lazy-loads `RelationGraph` via `React.lazy` + `Suspense` (fallback
  "Φόρτωση γραφήματος…"). Initial bundle 686→249 kB (gzip 218→79); cytoscape lives
  in a separate 438 kB chunk fetched only when the graph panel shows. >500 kB build
  warning gone. Next polish: extend `labels.ts` maps as new tags appear, and the
  bilingual el↔en mode (deferred until the Greek-only version is complete).

## Hard rules
- Never ingest Triantafyllides / Academy of Athens / e-lexicon — link-out only.
- Every displayed item keeps its `source`. AI explains; sources define.
- See `.claude/skills/lexorama-pipeline/SKILL.md` for the enforced checklist.
