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

CREATE TABLE IF NOT EXISTS source_attributions (
    source_name      TEXT PRIMARY KEY,
    source_url       TEXT,
    license          TEXT,
    attribution_text TEXT,
    retrieved_at     TEXT
);
