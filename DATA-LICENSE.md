# Data licensing — read before publishing a database

The code in this repository is MIT (see `LICENSE`). **The data is not.** Each source
carries its own terms, they are not all compatible, and at least one is
**non-commercial**. This file records the real position, not the aspirational one.

Machine-readable per-source metadata lives in `SOURCE_META`
(`pipelines/ingest/ingest_kaikki.py`) and is written into the `source_attributions`
table on every ingest; `GET /api/attributions` and the in-app `/licensing` page render it.

## Sources and terms

| Source | Tables it feeds | Licence | Commercial use |
|---|---|---|---|
| Wiktionary el + en (via Kaikki/wiktextract) | `lemmas`, `senses`, `forms`, `relations`, `etymology`, `etymons`, `pronunciations`, `descendants`, `gloss_index` | CC BY-SA 4.0 **and** GFDL | Yes, with share-alike |
| Open Multilingual Wordnet (`omw-el`) | `relations` (`source='omw-el'`) | Apache-2.0 | Yes |
| Princeton WordNet 3.0 (via OMW `expand`) | the is-a structure of the above | WordNet 3.0 Licence | Yes, with notice |
| FrequencyWords / OpenSubtitles (hermitdave) | `frequency` | CC BY-SA 4.0 | Yes, with share-alike |
| **Wortschatz Leipzig Corpora Collection** | `collocations`, `corpus_examples`, `semantic_neighbors`, `frequency_timeseries`, and the diachronic layers | **CC BY-NC** | **NO** |

Leipzig's terms: *"The data and applications provided by the Wortschatz Leipzig project
are protected by copyright and made available free of charge for private and scientific
use under the Creative Commons licence CC BY-NC."* — <https://wortschatz-leipzig.de/en/usage>

## The conflict, stated plainly

`docs/licensing.md` and the in-app `/licensing` page say the derived database is
redistributed under **CC BY-SA 4.0**. That claim is **not supportable for any build that
contains Leipzig-derived data**:

- CC BY-SA 4.0 permits commercial use. CC BY-NC forbids it.
- NC content cannot be relicensed under BY-SA, and the two cannot be merged into a
  single work offered under BY-SA alone.
- The restriction propagates to anything derived from that data — including collocation
  scores, example sentences, semantic neighbours and every diachronic measure, which are
  derivatives of the corpus even though they are not verbatim text.

Additionally, `corpus_examples` redistributes **verbatim corpus sentences** (276,769 rows
in the pre-rebuild database), and the per-sentence publisher/attribution file shipped in
the Leipzig archive (`*-sources.txt`) is never read by the ingest — so those sentences
carry no attribution to their original publisher (audit F25).

## Current build status

**The database built by the current pipeline contains no Leipzig data.** After the
schema_version 2 rebuild, `source_attributions` holds exactly four sources:

    el-wiktionary        CC BY-SA 4.0 / GFDL
    en-wiktionary        CC BY-SA 4.0 / GFDL
    omw-el               Apache-2.0 / WordNet 3.0
    opensubtitles-freq   CC BY-SA 4.0

All four permit commercial use, so **this build is redistributable under CC BY-SA 4.0**
as the site claims. Verify with `GET /api/attributions` before trusting that statement —
it is a property of the build, not of the project.

Re-running the Leipzig layers (collocations, examples, neighbours, frequency timeseries,
diachronic) **reintroduces the NC restriction** and invalidates the CC BY-SA 4.0 claim.
That is a decision, not an accident — see `BACKLOG.md` D6.

## Options if the Leipzig layers are wanted

1. **Keep them, drop the BY-SA claim.** Publish the DB as CC BY-NC-SA and accept that
   the project is non-commercial. Simplest, and consistent with a free public dictionary.
2. **Replace the corpus** with a commercially-usable Greek corpus (e.g. a CC BY or public
   -domain source, or Wikipedia dumps under CC BY-SA) and rebuild those layers.
3. **Ship the layers as a separate, clearly-labelled NC dataset** and keep the core
   lexical DB BY-SA. Requires the `sources` registry with a `redistributable` column that
   the redesign specifies (`docs/REDESIGN.md` §Phase 2).
4. **Serve but do not redistribute.** Offer the layers through the API without publishing
   a downloadable snapshot. Reduces but does not eliminate the issue.

None of these is chosen yet. Until one is, do not publish a database snapshot that
contains Leipzig-derived rows.

## Obligations that apply to every build

- **Attribution** for each source, with a link and a statement that the data was modified.
  Rendered in the site footer and at `/licensing`.
- **Share-alike** on the Wiktionary-derived portion: a redistributed database must be
  offered under CC BY-SA 4.0 (or later) with the same freedoms.
- **WordNet 3.0 notice** must accompany any redistribution of the OMW-derived relations.
- **EU sui generis database right**: CC 4.0 licences explicitly waive the licensor's sui
  generis rights, so BY-SA 4.0 sources are safe; verify separately for any source added
  under a pre-4.0 licence.

## Hard rule (unchanged)

Never ingest text from Triantafyllides (greek-language.gr), the Academy of Athens
Χρηστικό Λεξικό, or e-lexicon.gr. Link out only. These are not open-licensed and no
amount of transformation makes them redistributable.
