-- Λεξόραμα lexical store (M0/M1). SQLite; portable to Postgres later.
-- A lemma is unique per (normalized_lemma, pos). el + en Wiktionary entries for
-- the same word merge onto one lemma row; their senses/forms keep their source.

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS lemmas (
    id               INTEGER PRIMARY KEY,
    lemma            TEXT NOT NULL,          -- display form, accents preserved
    normalized_lemma TEXT NOT NULL,          -- search key from normalize()
    pos              TEXT,                   -- noun / verb / adj / ...
    gender           TEXT,
    language         TEXT DEFAULT 'el',
    sources          TEXT,                   -- comma list: "el-wiktionary,en-wiktionary"
    UNIQUE (normalized_lemma, pos)
);
CREATE INDEX IF NOT EXISTS idx_lemmas_norm ON lemmas (normalized_lemma);

CREATE TABLE IF NOT EXISTS senses (
    id          INTEGER PRIMARY KEY,
    lemma_id    INTEGER NOT NULL REFERENCES lemmas(id),
    sense_index INTEGER,
    gloss       TEXT NOT NULL,
    tags        TEXT,                        -- json array as text
    examples    TEXT,                        -- json array as text
    source      TEXT NOT NULL                -- el-wiktionary | en-wiktionary
);
CREATE INDEX IF NOT EXISTS idx_senses_lemma ON senses (lemma_id);

CREATE TABLE IF NOT EXISTS forms (
    id              INTEGER PRIMARY KEY,
    lemma_id        INTEGER NOT NULL REFERENCES lemmas(id),
    form            TEXT NOT NULL,           -- display form, accents preserved
    normalized_form TEXT NOT NULL,           -- search key
    features        TEXT,                    -- json array of grammatical tags
    source          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_forms_norm ON forms (normalized_form);
CREATE INDEX IF NOT EXISTS idx_forms_lemma ON forms (lemma_id);

CREATE TABLE IF NOT EXISTS relations (
    id               INTEGER PRIMARY KEY,
    source_lemma_id  INTEGER NOT NULL REFERENCES lemmas(id),
    target_lemma_id  INTEGER REFERENCES lemmas(id),
    target_text      TEXT,                   -- when target lemma not in store yet
    relation_type    TEXT NOT NULL,          -- synonym|antonym|hypernym|hyponym|derived|related
    weight           REAL DEFAULT 1.0,
    source           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_relations_src ON relations (source_lemma_id);

-- Unified lookup surface: lemmas AND inflected forms, both pre-normalized.
CREATE TABLE IF NOT EXISTS search_index (
    id               INTEGER PRIMARY KEY,
    normalized_surface TEXT NOT NULL,
    surface          TEXT NOT NULL,
    lemma_id         INTEGER NOT NULL REFERENCES lemmas(id),
    surface_type     TEXT NOT NULL,          -- lemma | form
    features         TEXT,                   -- form features, for the "why this form" card
    rank_weight      REAL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_search_norm ON search_index (normalized_surface);

-- Etymology prose, one row per lemma (el-wiktionary preferred over en).
CREATE TABLE IF NOT EXISTS etymology (
    lemma_id INTEGER PRIMARY KEY REFERENCES lemmas(id),
    text     TEXT,                            -- prose etymology, accents preserved
    source   TEXT NOT NULL
);

-- Structured etymological origins parsed from Wiktionary's {{inh}}/{{der}}/{{bor}}/
-- {{cog}}/{{cal}} templates. These become typed+sourced ORIGIN edges in the graph.
-- Targets are usually cross-language ancestors (grc, ine-pro, la…), so they carry a
-- language code + term rather than a Modern-Greek lemma id.
CREATE TABLE IF NOT EXISTS etymons (
    id        INTEGER PRIMARY KEY,
    lemma_id  INTEGER NOT NULL REFERENCES lemmas(id),
    relation  TEXT NOT NULL,                  -- inherited|borrowed|derived|calque|cognate
    lang_code TEXT,                           -- grc, grc-koi, gkm, ine-pro, la, tr, it…
    term      TEXT NOT NULL,                  -- the source-language word
    source    TEXT NOT NULL,
    seq       INTEGER DEFAULT 0               -- order within the etymology chain
);
CREATE INDEX IF NOT EXISTS idx_etymons_lemma ON etymons (lemma_id);
-- Reverse lookup: all Modern-Greek lemmas descending from a given ancestor term.
-- Powers the "ομόρριζες λέξεις" (same-root cognate) cross-links on the word page.
CREATE INDEX IF NOT EXISTS idx_etymons_ancestor ON etymons (lang_code, term);

-- IPA pronunciation(s) per lemma, from Wiktionary's `sounds` field. A lemma may
-- carry more than one (regional/alternate readings, e.g. ήλιο /ˈi.li.o/ ~ /ˈi.ʎo/),
-- so (lemma_id, ipa) is the key and INSERT OR IGNORE keeps the pass idempotent.
CREATE TABLE IF NOT EXISTS pronunciations (
    lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
    ipa      TEXT NOT NULL,                   -- IPA transcription, e.g. ˈxɾo.ma
    source   TEXT NOT NULL,
    seq      INTEGER DEFAULT 0,
    PRIMARY KEY (lemma_id, ipa)
);

-- Descendants: words in OTHER languages formed from this Greek lemma (the forward
-- mirror of `etymons`). Sourced from en-wiktionary's `descendants` field, e.g.
-- Ελλάδα -> English "Ellada", Russian "Элλάδα". Cross-language, so they carry a
-- language code + term (+ optional romanisation), never a Modern-Greek lemma id.
CREATE TABLE IF NOT EXISTS descendants (
    id        INTEGER PRIMARY KEY,
    lemma_id  INTEGER NOT NULL REFERENCES lemmas(id),
    relation  TEXT NOT NULL,                  -- borrowed|inherited|calque|derived (raw_tag)
    lang_code TEXT,
    lang_name TEXT,                            -- display name from the dump ("Russian")
    term      TEXT NOT NULL,                  -- the descendant word in that language
    roman     TEXT,                            -- optional romanisation
    source    TEXT NOT NULL,
    seq       INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_descendants_lemma ON descendants (lemma_id);

-- Corpus frequency per lemma, aggregated from a word-frequency list (e.g. the
-- OpenSubtitles-derived FrequencyWords list) by summing each lemma's inflected
-- surface counts via search_index. `zipf` is the standard log10(per-billion)
-- scale (~1 rare .. ~7 very common); `band` is a coarse label for display.
CREATE TABLE IF NOT EXISTS frequency (
    lemma_id INTEGER PRIMARY KEY REFERENCES lemmas(id),
    count    INTEGER NOT NULL,                -- summed corpus count over the lemma's forms
    rank     INTEGER,                          -- 1 = most frequent among matched lemmas
    zipf     REAL,                             -- log10(count per billion words)
    band     TEXT,                             -- very_common|common|moderate|uncommon|rare
    source   TEXT NOT NULL
);

-- Collocations: words that statistically co-occur with a lemma in a corpus
-- (e.g. φορτίο ~ βαρύ, μεταφορά, πλοίο). Layered from a co-occurrence dataset
-- (Leipzig Wortschatz) by resolving each corpus word to a lemma via search_index
-- and keeping the top collocates by association score. collocate_lemma_id links
-- the chip to a word page when the collocate is itself a known lemma.
CREATE TABLE IF NOT EXISTS collocations (
    id                  INTEGER PRIMARY KEY,
    lemma_id            INTEGER NOT NULL REFERENCES lemmas(id),
    collocate           TEXT NOT NULL,           -- the co-occurring word (display)
    collocate_lemma_id  INTEGER REFERENCES lemmas(id),
    score               REAL,                     -- association strength (log-likelihood)
    source              TEXT NOT NULL,
    seq                 INTEGER DEFAULT 0         -- rank within this lemma (0 = strongest)
);
CREATE INDEX IF NOT EXISTS idx_collocations_lemma ON collocations (lemma_id);

-- KWIC concordances: real example sentences per lemma, mined from a sentence
-- corpus (Wortschatz Leipzig ell_news). Wiktionary examples are sparse, so we
-- surface authentic usage: each sentence is tokenized, every token resolved to a
-- lemma via search_index, and the cleanest few sentences are kept per lemma
-- (ranked by a readability heuristic). seq 0 = best. Distinct from `senses.examples`
-- (curated, dictionary-authored) — these are emergent corpus usage, source-badged.
CREATE TABLE IF NOT EXISTS corpus_examples (
    id        INTEGER PRIMARY KEY,
    lemma_id  INTEGER NOT NULL REFERENCES lemmas(id),
    sentence  TEXT NOT NULL,
    source    TEXT NOT NULL,
    seq       INTEGER DEFAULT 0         -- rank within this lemma (0 = best)
);
CREATE INDEX IF NOT EXISTS idx_corpus_examples_lemma ON corpus_examples (lemma_id);

-- Semantic neighbors: words with similar meaning/usage, from a word-embedding
-- model (word2vec) trained on the sentence corpus. Distinct from collocations
-- (which co-OCCUR) — neighbors are words that appear in similar CONTEXTS, i.e.
-- distributional synonyms/near-synonyms (καναπές ~ πολυθρόνα, τρέχω ~ περπατάω).
-- Tokens are trained/queried in the normalized key space and resolved back to
-- lemmas; only neighbors that resolve to a known lemma are kept (so each links).
-- This is the static (single-corpus) precursor to Layer C diachronic drift.
CREATE TABLE IF NOT EXISTS semantic_neighbors (
    id                INTEGER PRIMARY KEY,
    lemma_id          INTEGER NOT NULL REFERENCES lemmas(id),
    neighbor          TEXT NOT NULL,            -- display lemma of the neighbor
    neighbor_lemma_id INTEGER REFERENCES lemmas(id),
    score             REAL,                     -- cosine similarity (0..1)
    source            TEXT NOT NULL,
    seq               INTEGER DEFAULT 0         -- rank within this lemma (0 = closest)
);
CREATE INDEX IF NOT EXISTS idx_semantic_neighbors_lemma ON semantic_neighbors (lemma_id);

-- ── Diachronic layers (B & C) ──────────────────────────────────────────────
-- These are CORPUS-TAGGED and per-time-slice. The cardinal rule: a time series
-- is only valid WITHIN one consistent corpus (mixing registers across years would
-- read corpus change as language change). So every row carries `corpus`
-- (parliament | news) and each corpus is its own internally-comparable axis; the
-- UI renders them as separate, labeled series — never a single pooled number.

-- Layer B: frequency over time. per_million normalizes for slice size so years
-- (and corpora) are comparable on the same y-axis.
CREATE TABLE IF NOT EXISTS frequency_timeseries (
    id          INTEGER PRIMARY KEY,
    lemma_id    INTEGER NOT NULL REFERENCES lemmas(id),
    corpus      TEXT NOT NULL,            -- parliament | news
    year        INTEGER NOT NULL,
    count       INTEGER NOT NULL,         -- summed over the lemma's forms in that slice
    per_million REAL,                     -- count / slice_tokens * 1e6
    source      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_freq_ts_lemma ON frequency_timeseries (lemma_id, corpus, year);

-- Layer C: semantic drift. One row per lemma per corpus: how far its meaning moved
-- between the earliest and latest slice (cosine distance in Procrustes-aligned
-- embedding space), the standard Hamilton et al. (2016) measure.
CREATE TABLE IF NOT EXISTS diachronic_drift (
    id          INTEGER PRIMARY KEY,
    lemma_id    INTEGER NOT NULL REFERENCES lemmas(id),
    corpus      TEXT NOT NULL,
    drift_score REAL NOT NULL,            -- cosine distance, first vs last aligned slice
    neighbor_overlap REAL,                -- Gonen 2020: 1 - Jaccard(top-k neighbors then, now); freq-robust
    first_year  INTEGER NOT NULL,
    last_year   INTEGER NOT NULL,
    n_slices    INTEGER NOT NULL,         -- slices the lemma had a vector in
    change_point_year INTEGER,            -- year of the largest single-step jump in the per-slice trajectory (#35); NULL when not a clear outlier (#44)
    change_point_score REAL,              -- robust z of the winning step vs the other steps; kept even when suppressed (#44)
    drift_ci_lo REAL,                     -- 2.5th-pct lower bound of endpoint-bootstrap drift (#36/#43); NULL until bootstrap run
    drift_ci_hi REAL,                     -- 97.5th pct of endpoint-bootstrap drift (#36)
    drift_significant INTEGER,            -- 1 = BH-FDR reject at q<0.05: real drift exceeds same-freq noise (#2/#36)
    drift_q     REAL,                     -- BH-FDR adjusted p-value across all tested lemmas (#2)
    drift_score_boot REAL,                -- bootstrap-mean drift = preferred point estimate (#50); NULL until bootstrap run
    source      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drift_lemma ON diachronic_drift (lemma_id, corpus);

-- Layer C trajectory (#35): the SHAPE of meaning change, not just the endpoints.
-- Each dense slice is Procrustes-aligned to the reference (first dense) slice and
-- we record the cosine distance of the lemma's vector in that slice from its
-- reference vector. A word that drifted and reverted (low first↔last drift but a
-- high mid-series bump) is now visible; the change-point year is the steepest step.
CREATE TABLE IF NOT EXISTS diachronic_trajectory (
    id                INTEGER PRIMARY KEY,
    lemma_id          INTEGER NOT NULL REFERENCES lemmas(id),
    corpus            TEXT NOT NULL,            -- parliament | news
    year              INTEGER NOT NULL,
    distance_from_ref REAL NOT NULL,            -- cosine distance vs the reference (first dense) slice, aligned
    source            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_diac_traj_lemma ON diachronic_trajectory (lemma_id, corpus, year);

-- Layer C companion: a lemma's nearest neighbors WITHIN a given slice — the
-- "γείτονες τότε / γείτονες τώρα" comparison. Neighbors are within-slice (no
-- alignment needed for a single model's own similarity), resolved to lemmas.
CREATE TABLE IF NOT EXISTS diachronic_neighbors (
    id                INTEGER PRIMARY KEY,
    lemma_id          INTEGER NOT NULL REFERENCES lemmas(id),
    corpus            TEXT NOT NULL,
    year              INTEGER NOT NULL,
    neighbor          TEXT NOT NULL,
    neighbor_lemma_id INTEGER REFERENCES lemmas(id),
    score             REAL,
    source            TEXT NOT NULL,
    seq               INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_diac_neigh_lemma ON diachronic_neighbors (lemma_id, corpus, year);

-- Supervised domain attribution (#38). The "ανά πεδίο" exploration used to assign
-- a lemma to a subject field purely by intersecting senses.tags with a fixed field
-- list — defensible only for the ~15k lemmas Wiktionary happens to topic-tag. This
-- table is the distant-supervision upgrade: a classifier trained on the clean
-- single-domain-tagged lemmas (gold labels) over corpus embedding vectors predicts
-- a field for every content lemma that has a vector. Gold tags are kept verbatim
-- (source='wiktionary-tag', score=1) and stay authoritative; classifier rows
-- (source='classifier', score = softmax confidence) only ADD coverage for lemmas
-- Wiktionary never tagged. "Sources define, AI explains": every row carries its
-- provenance so the UI can mark a prediction as inferred.
CREATE TABLE IF NOT EXISTS lemma_domain_pred (
    id        INTEGER PRIMARY KEY,
    lemma_id  INTEGER NOT NULL REFERENCES lemmas(id),
    domain    TEXT NOT NULL,            -- predicted/tagged field (English key from _FIELD_DOMAINS)
    score     REAL NOT NULL,            -- softmax confidence 0–1 (1.0 for gold tags)
    rank      INTEGER NOT NULL DEFAULT 1, -- 1 = top prediction for this lemma
    source    TEXT NOT NULL             -- 'wiktionary-tag' (gold) | 'classifier' (inferred)
);
CREATE INDEX IF NOT EXISTS idx_ldp_lemma ON lemma_domain_pred (lemma_id);
CREATE INDEX IF NOT EXISTS idx_ldp_domain ON lemma_domain_pred (domain, source, score);

-- Cross-language search index (#39, el↔en). The en-Wiktionary edition gives an
-- English gloss for ~32k Greek lemmas (e.g. αετός → "eagle; kite (toy)"). This
-- table lets a user type an English word and resolve to the Greek lemma: we
-- extract the clean leading headword phrase(s) from each English gloss and map
-- them back to the lemma. Built by build_gloss_index.py from senses where
-- source LIKE 'en%'. The Greek dictionary stays primary — this is a lookup aid,
-- and every row keeps its 'en-wiktionary' provenance.
CREATE TABLE IF NOT EXISTS gloss_index (
    id          INTEGER PRIMARY KEY,
    en_term     TEXT NOT NULL,            -- normalized English headword/short phrase
    lemma_id    INTEGER NOT NULL REFERENCES lemmas(id),
    rank_weight REAL DEFAULT 1.0,         -- leading sense of a gloss > later ones
    source      TEXT NOT NULL             -- 'en-wiktionary'
);
CREATE INDEX IF NOT EXISTS idx_gloss_en ON gloss_index (en_term);
CREATE INDEX IF NOT EXISTS idx_gloss_lemma ON gloss_index (lemma_id);

-- Query log (data flywheel): one row per /api/search call — the raw query, its
-- normalized key, whether it resolved, and the top lemma it resolved to. Powers
-- (a) spell-correction training, (b) gap analysis (high-volume UNRESOLVED queries
-- = words users want that we lack), and (c) a modern, dated mini-corpus of real
-- Greek lookups. Written by the API at runtime, not by ingest. No PII: query only.
CREATE TABLE IF NOT EXISTS query_log (
    id           INTEGER PRIMARY KEY,
    query        TEXT NOT NULL,
    normalized   TEXT,
    resolved     INTEGER NOT NULL,        -- 1 if it produced any result
    top_lemma_id INTEGER REFERENCES lemmas(id),
    result_count INTEGER,
    via          TEXT,                    -- direct | greeklish
    ts           TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_query_log_norm ON query_log (normalized);
CREATE INDEX IF NOT EXISTS idx_query_log_resolved ON query_log (resolved);

CREATE TABLE IF NOT EXISTS source_attributions (
    source_name      TEXT PRIMARY KEY,
    source_url       TEXT,
    license          TEXT,
    attribution_text TEXT,
    retrieved_at     TEXT
);
