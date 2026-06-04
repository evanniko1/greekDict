# Data sources

| Source | Role | Milestone | Notes |
|---|---|---|---|
| Kaikki / Wiktionary (el) | Native Greek definitions, senses, forms | M1 | Greek-edition extract |
| Kaikki / Wiktionary (en, Greek entries) | Often better inflection tables + etymology | M1 | Merge onto el lemmas |
| Greek WordNet / OMW | Typed semantic edges (synonym/hyper/hyponym) | M4 | Thin/uneven — labeled edges only |
| Greek embeddings (fastText / GreekBERT) | Soft semantic-neighbour edges | M4+ | Fills WordNet sparsity; visually distinguished |
| GR-NLP-TOOLKIT | Greeklish + POS/morph tagging | M5 | Does NOT generate paradigms |
| GreekLex | Frequency + orthographic neighbours | post-MVP | Cut from MVP |

## Kaikki dump notes

- Verify current URLs at https://kaikki.org/ — paths change per dump.
- el extract = Greek-language Wiktionary. en extract = English Wiktionary,
  filter `lang_code == "el"` (the ingest script does this).
- Entry shape used: `word`, `pos`, `lang_code`, `senses[].glosses`,
  `senses[].tags`, `senses[].examples[].text`, `forms[].form`, `forms[].tags`.
- `forms` entries tagged `table-tags` / `inflection-template` are layout
  artifacts, not real forms — filtered out during ingest.

## Why both el and en

el gives native-language glosses Greek users expect; en frequently has
cleaner, more complete declension/conjugation tables and etymology for the same
word. Merging by `(normalized_lemma, pos)` gives the union.

## Etymology chains (`etymons` table)

- **en dump** carries `etymology_templates` ({{inh}}/{{der}}/{{bor}}/{{cal}}/{{cog}})
  → parsed directly into typed etymons.
- **el dump** has NO templates, only prose `etymology_text` with a consistent
  grammar: `headword < (marker) LANGUAGE term < (marker) LANGUAGE older < …`.
  `parse_el_etymology_prose` walks the WHOLE " < " chain and emits one
  `(relation, lang_code, term, seq)` per step that names a recognised language
  (`seq` = chain order, 0 = immediate ancestor). Steps with no recognised
  language (internal Greek morphology, redirects, "λείπει η ετυμολογία") are
  skipped — we never assert an ancestor we can't type. Connector words between a
  language and its term ("πρωτοϊνδοευρωπαϊκή **ρίζα** *reh-") are skipped.
- **Multi-hop reparse:** the original ingest parsed only the immediate ancestor.
  `python -m pipelines.ingest.reparse_etymology` re-applies the full-chain parser
  to the prose ALREADY in the `etymology` table (no 1.4 GB re-stream), faithful to
  `store_etymology`'s precedence (el overrides en). Result: el etymons
  33,069 → **52,928**; lemmas with a chain 33,069 → **38,806**, of which
  **10,731** are genuine multi-hop (≥2 stages); 765 stale single-etymons cleaned.
  The graph endpoint renders these as a LINEAGE PATH (headword → grc-koi → la →
  ine-pro), and `EtymologyTimeline` now lights up for the multi-hop lemmas.
- **Cognate cross-links ("ομόρριζες λέξεις"):** the word payload's `cognates`
  field lists other Modern-Greek lemmas sharing one of this lemma's ancestors
  (same `lang_code`+`term`), ranked by ancestor specificity (tight roots first,
  mega-clusters >60 skipped), with the shared root shown. Backed by
  `idx_etymons_ancestor (lang_code, term)`.

## WordNet / OMW ingest notes (`source='omw-el'`)

- Pipeline: `python -m pipelines.ingest.ingest_wordnet`. Uses the `wn` library:
  `wn.Wordnet("omw-el:1.4", expand="omw-en:1.4")`. The Greek lexicon (`omw-el`)
  supplies the lemma→synset membership; the Princeton structure shared via the
  `omw-en` *expand* lexicon supplies the synset-to-synset relations (hypernym,
  hyponym). Run `wn.download('omw-en:1.4')` once so the dependency resolves.
- **Why we needed it:** Wiktionary gives plenty of `synonym`/`related`/`antonym`
  edges but almost no taxonomy — only ~130 hypernym/hyponym edges total. WordNet's
  whole point is the is-a hierarchy, so this importer fills that gap.
- **Edge contract** (every edge typed + sourced):
  - POS-matched — a wordnet noun sense only attaches to a `noun` lemma, never to
    a same-spelled verb/adjective homograph.
  - linked-only — an edge is emitted only when BOTH endpoints already exist as
    **single-word** lemmas we hold (`target_lemma_id` resolved). Multiword/
    periphrastic synset members produce no dangling text nodes.
  - idempotent — every prior `source='omw-el'` row is deleted first, so the
    importer replays cleanly after a wordnet refresh.
  - provenance — `source='omw-el'`, distinct from the wiktionary edges, so the
    graph view labels/styles wordnet edges separately (amber=hypernym,
    cyan=hyponym; tooltip shows `· omw-el`).
- **Result of the run:** 40,413 edges over 10,140 matched headwords —
  15,246 hypernym, 15,136 hyponym, 10,031 synonym. The graph endpoint
  (`/api/word/{lemma}/graph`) ranks these typed edges ahead of the ~186k
  `related` catch-all so a high-degree node still surfaces its taxonomy.
