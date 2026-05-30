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
