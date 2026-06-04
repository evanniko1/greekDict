# Licensing & attribution

## What we ingest

| Source | License | Obligation |
|---|---|---|
| Wiktionary (el + en) via Kaikki | CC BY-SA 3.0/4.0 + GFDL | Attribute; derived DB stays share-alike |
| Greek WordNet — `omw-el` 1.4 (M4) | Apache-2.0 | Attribute |
| Princeton WordNet — `omw-en` 1.4, used as *expand* structure (M4) | WordNet 3.0 License (BSD-style) | Attribute Princeton WordNet |
| GreekLex (later) | Academic citation | Cite the paper |

CC BY-SA share-alike is **compatible with a free app**. It only means: credit
the source, and anyone may reuse our derived lexical DB under the same terms.
Plan to publish a downloadable DB snapshot + attribution from day one.

## Hard "do not ingest" — reference / link-out only

These are copyrighted and explicitly restrict reproduction. Link to them; never
copy their text, definitions, or examples into our store:

- **Triantafyllides** dictionary (greek-language.gr) — copyright page forbids
  total/partial/paraphrased reproduction.
- **Academy of Athens Χρηστικό Λεξικό** — no open reuse terms.
- **e-lexicon.gr** — proprietary.

Inspiration for UX is fine. Their *content* is off-limits without written
permission.

## Per-panel provenance

Every displayed item carries a `source` tag (definition → Wiktionary, relation →
WordNet, etc.). Never silently merge human, Wiktionary, WordNet, corpus, or
AI-generated content. AI explains; sources define.

## How attribution is implemented

Two layers, deliberately separated:

1. **Provenance (per item).** Every sense/form/relation keeps its `source` and
   renders a small badge in the UI. This is the "do not silently merge" guarantee
   above — it is *not* the legal license notice.
2. **Legal attribution (centralised).** `ingest_kaikki.record_attribution()`
   writes one row per source into `source_attributions` (source_url, license,
   modification notice, `retrieved_at`) on every ingest — keyed by `source_name`,
   idempotent. `GET /api/attributions` exposes it. The frontend renders it in a
   **persistent site footer** (present on every page, so deep-linked word pages
   are covered) that links to **`/licensing`**, where the full CC BY-SA 4.0 + GFDL
   text, source links, the "data was modified" notice, and the ShareAlike
   obligation are spelled out. We do *not* repeat the full legal notice on every
   term — the badges already carry provenance.

ShareAlike note: because Wiktionary is CC BY-SA, our derived lexical DB is
redistributed under CC BY-SA 4.0 (stated on `/licensing`). Ship a downloadable DB
snapshot + this attribution alongside any public release.
