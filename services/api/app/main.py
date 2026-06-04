"""Λεξόραμα API (M0/M1).

The core endpoint is /api/search: it resolves a raw Greek (or Greeklish) query
to a lemma and, crucially, EXPLAINS the match — e.g. an inflected form maps back
to its lemma with grammatical features. That resolution+explanation is the whole
point of the product.

Run:
    uvicorn services.api.app.main:app --reload
    (set LEXORAMA_DB to point at the sqlite file; defaults to data/db/lexorama.sqlite)
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query

# Make the normalization module importable from the pipeline package.
import sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipelines", "ingest"))
from normalize_greek import normalize, greeklish_to_greek, greeklish_candidates  # noqa: E402

DB_PATH = os.environ.get("LEXORAMA_DB", os.path.join(ROOT, "data", "db", "lexorama.sqlite"))

app = FastAPI(title="Λεξόραμα API", version="0.1.0")


def db() -> sqlite3.Connection:
    if not os.path.exists(DB_PATH):
        raise HTTPException(503, f"Database not built. Expected at {DB_PATH}. Run the ingest pipeline.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Forward-compat: a DB built before the etymology feature lacks these tables.
    # Creating them empty (idempotent) keeps /api/word working without a re-ingest;
    # they fill in on the next ingest pass. CREATE IF NOT EXISTS is a no-op once present.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS etymology ("
        "lemma_id INTEGER PRIMARY KEY REFERENCES lemmas(id), text TEXT, source TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS etymons ("
        "id INTEGER PRIMARY KEY, lemma_id INTEGER NOT NULL REFERENCES lemmas(id), "
        "relation TEXT NOT NULL, lang_code TEXT, term TEXT NOT NULL, source TEXT NOT NULL, "
        "seq INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS pronunciations ("
        "lemma_id INTEGER NOT NULL REFERENCES lemmas(id), ipa TEXT NOT NULL, "
        "source TEXT NOT NULL, seq INTEGER DEFAULT 0, PRIMARY KEY (lemma_id, ipa))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS descendants ("
        "id INTEGER PRIMARY KEY, lemma_id INTEGER NOT NULL REFERENCES lemmas(id), "
        "relation TEXT NOT NULL, lang_code TEXT, lang_name TEXT, term TEXT NOT NULL, "
        "roman TEXT, source TEXT NOT NULL, seq INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS frequency ("
        "lemma_id INTEGER PRIMARY KEY REFERENCES lemmas(id), count INTEGER NOT NULL, "
        "rank INTEGER, zipf REAL, band TEXT, source TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS collocations ("
        "id INTEGER PRIMARY KEY, lemma_id INTEGER NOT NULL REFERENCES lemmas(id), "
        "collocate TEXT NOT NULL, collocate_lemma_id INTEGER REFERENCES lemmas(id), "
        "score REAL, source TEXT NOT NULL, seq INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS corpus_examples ("
        "id INTEGER PRIMARY KEY, lemma_id INTEGER NOT NULL REFERENCES lemmas(id), "
        "sentence TEXT NOT NULL, source TEXT NOT NULL, seq INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS semantic_neighbors ("
        "id INTEGER PRIMARY KEY, lemma_id INTEGER NOT NULL REFERENCES lemmas(id), "
        "neighbor TEXT NOT NULL, neighbor_lemma_id INTEGER REFERENCES lemmas(id), "
        "score REAL, source TEXT NOT NULL, seq INTEGER DEFAULT 0)"
    )
    # Query log (data flywheel): every search, whether it resolved, and to what.
    # Powers spell-correction, gap analysis (what users want that we lack), and a
    # modern dated mini-corpus of real Greek lookups. No PII — query text only.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS query_log ("
        "id INTEGER PRIMARY KEY, query TEXT NOT NULL, normalized TEXT, "
        "resolved INTEGER NOT NULL, top_lemma_id INTEGER, result_count INTEGER, "
        "via TEXT, ts TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    # Diachronic layers (B & C). Each row is tagged with a `corpus` (parliament |
    # news) because a time series is only valid WITHIN one consistent corpus; the
    # UI renders one labeled series per corpus and never merges them.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS frequency_timeseries ("
        "id INTEGER PRIMARY KEY, lemma_id INTEGER NOT NULL REFERENCES lemmas(id), "
        "corpus TEXT NOT NULL, year INTEGER NOT NULL, count INTEGER NOT NULL, "
        "per_million REAL, source TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS diachronic_drift ("
        "id INTEGER PRIMARY KEY, lemma_id INTEGER NOT NULL REFERENCES lemmas(id), "
        "corpus TEXT NOT NULL, drift_score REAL, first_year INTEGER, last_year INTEGER, "
        "n_slices INTEGER, source TEXT NOT NULL)"
    )
    # Forward-compat: the neighbor_overlap column (Gonen 2020 measure) was added
    # after the first diachronic build. ADD COLUMN if an older DB lacks it.
    _drift_cols = {r[1] for r in conn.execute("PRAGMA table_info(diachronic_drift)")}
    if "neighbor_overlap" not in _drift_cols:
        conn.execute("ALTER TABLE diachronic_drift ADD COLUMN neighbor_overlap REAL")
    if "change_point_year" not in _drift_cols:
        conn.execute("ALTER TABLE diachronic_drift ADD COLUMN change_point_year INTEGER")
    if "change_point_score" not in _drift_cols:  # #44: confidence of the change point
        conn.execute("ALTER TABLE diachronic_drift ADD COLUMN change_point_score REAL")
    # Forward-compat: drift confidence intervals + significance (#36), populated
    # by bootstrap_drift.py. NULL until that pipeline has run for the corpus.
    for _c in ("drift_ci_lo", "drift_ci_hi", "drift_q", "drift_score_boot"):
        if _c not in _drift_cols:
            conn.execute(f"ALTER TABLE diachronic_drift ADD COLUMN {_c} REAL")
    if "drift_significant" not in _drift_cols:
        conn.execute("ALTER TABLE diachronic_drift ADD COLUMN drift_significant INTEGER")
    # Layer C trajectory (#35): per-slice cosine distance from the reference slice.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS diachronic_trajectory ("
        "id INTEGER PRIMARY KEY, lemma_id INTEGER NOT NULL REFERENCES lemmas(id), "
        "corpus TEXT NOT NULL, year INTEGER NOT NULL, distance_from_ref REAL NOT NULL, "
        "source TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_diac_traj_lemma "
        "ON diachronic_trajectory (lemma_id, corpus, year)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS diachronic_neighbors ("
        "id INTEGER PRIMARY KEY, lemma_id INTEGER NOT NULL REFERENCES lemmas(id), "
        "corpus TEXT NOT NULL, year INTEGER NOT NULL, neighbor TEXT NOT NULL, "
        "neighbor_lemma_id INTEGER REFERENCES lemmas(id), score REAL, "
        "source TEXT NOT NULL, seq INTEGER DEFAULT 0)"
    )
    # Materialized cache for the expensive, fully-deterministic explore endpoints
    # (trends, compare). Keyed by endpoint+params; `sig` is a fingerprint of the
    # underlying Layer-B/C row counts, so a re-ingest auto-invalidates stale rows
    # without any pipeline coupling. See _cache_get / _cache_put.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS explore_cache ("
        "cache_key TEXT PRIMARY KEY, sig TEXT NOT NULL, "
        "payload TEXT NOT NULL, built_at TEXT NOT NULL)"
    )
    # Supervised domain attribution (#38). Guard so the API serves the legacy
    # senses.tags fallback gracefully even before classify_domains.py has run.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS lemma_domain_pred ("
        "id INTEGER PRIMARY KEY, lemma_id INTEGER NOT NULL, domain TEXT NOT NULL, "
        "score REAL NOT NULL, rank INTEGER NOT NULL DEFAULT 1, source TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ldp_lemma ON lemma_domain_pred (lemma_id)"
    )
    # Cross-language (en→el) lookup index (#39). Guard so search degrades to
    # Greek-only gracefully before build_gloss_index.py has run.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS gloss_index ("
        "id INTEGER PRIMARY KEY, en_term TEXT NOT NULL, lemma_id INTEGER NOT NULL, "
        "rank_weight REAL DEFAULT 1.0, source TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_gloss_en ON gloss_index (en_term)"
    )
    return conn


def _en_key(q: str) -> str:
    """Normalize a query as an English lookup key for `gloss_index` (#39): lower,
    collapse whitespace, strip edge punctuation. Mirrors build_gloss_index's
    phrase normalization so 'Eagle.' and 'eagle' both hit αετός."""
    s = " ".join(q.lower().split())
    return s.strip(" .,;:!?\"'()[]")


def _features_label(features_json: str | None) -> str | None:
    if not features_json:
        return None
    try:
        tags = json.loads(features_json)
    except (json.JSONDecodeError, TypeError):
        return None
    return ", ".join(tags) if tags else None


def _resolve_lemma_ids(conn: sqlite3.Connection, surface: str) -> list[int]:
    """Resolve a raw surface to lemma id(s), in display priority order.

    A word page may be requested by its canonical lemma OR by any inflected
    surface ("Ηλεκτρολόγων" → "Ηλεκτρολόγος"). We try a direct lemma hit first,
    then fall back through `search_index` (lemmas + inflected forms, the same
    surface /api/search resolves against), then a Greeklish widening. This keeps
    the word page reachable for anything search can find.
    """
    key = normalize(surface)
    # Order homographs the way /api/search does, so the word page leads with the
    # entry the user actually navigated to: an EXACT-case lemma match first
    # (/word/αετός → the bird; /word/Αετός → the placename), then by corpus
    # frequency, then id for determinism. Without this a rarer proper noun (Αετός,
    # id 345) outranked the common noun (αετός, id 3047) purely on insertion order.
    direct = [r["id"] for r in conn.execute(
        """SELECT l.id FROM lemmas l
           LEFT JOIN frequency fr ON fr.lemma_id = l.id
           WHERE l.normalized_lemma = ?
           ORDER BY (l.lemma = ?) DESC, COALESCE(fr.rank, 1000000000) ASC, l.id ASC""",
        (key, surface.strip()),
    )]
    if direct:
        return direct

    # Greeklish widening: try the plausible spellings, most-frequent lemma first
    # (so /word/zoi lands on ζωή, not a rarer ζοι-like form).
    cand_keys: list[str] = []
    ck_seen: set[str] = set()
    for c in [key] + greeklish_candidates(surface):
        ck = normalize(c)
        if ck and ck not in ck_seen:
            ck_seen.add(ck)
            cand_keys.append(ck)
    if not cand_keys:
        return []
    qmarks = ",".join("?" * len(cand_keys))
    ids: list[int] = []
    seen: set[int] = set()
    for row in conn.execute(
        f"""SELECT si.lemma_id, COALESCE(fr.rank, 1000000000) AS freq_rank, si.rank_weight
            FROM search_index si
            LEFT JOIN frequency fr ON fr.lemma_id = si.lemma_id
            WHERE si.normalized_surface IN ({qmarks})
            ORDER BY freq_rank ASC, si.rank_weight DESC""",
        cand_keys,
    ):
        if row["lemma_id"] not in seen:
            seen.add(row["lemma_id"])
            ids.append(row["lemma_id"])
    return ids


@app.get("/api/search")
def search(q: str = Query(..., min_length=1), limit: int = 10):
    """Resolve a query to ranked lemma candidates, each with a match explanation."""
    conn = db()
    key = normalize(q)

    seen: set[int] = set()
    results: list[dict] = []

    def _emit(r, via: str, en_term: str | None = None) -> None:
        if r["lemma_id"] in seen:
            return
        seen.add(r["lemma_id"])
        is_form = r["surface_type"] == "form"
        feat = _features_label(r["features"])
        if via == "translation":
            # Cross-language hit (#39): the English gloss term resolved to a Greek
            # lemma. Show "eagle → αετός" so the bridge is explicit.
            match_type = "translation"
            explanation = f"{en_term} → {r['lemma']}" if en_term else r["lemma"]
        elif is_form:
            match_type = "inflected_form"
            explanation = f"{r['surface']} → {r['lemma']}"
            if feat:
                explanation += f" ({feat})"
        else:
            match_type = "lemma" if via == "direct" else "greeklish"
            explanation = r["lemma"]
        snippet_row = conn.execute(
            "SELECT gloss FROM senses WHERE lemma_id = ? ORDER BY sense_index LIMIT 1",
            (r["lemma_id"],),
        ).fetchone()
        results.append({
            "lemma_id": r["lemma_id"], "lemma": r["lemma"],
            "pos": r["pos"], "gender": r["gender"],
            "match_type": match_type, "matched_surface": r["surface"],
            "features": feat, "explanation": explanation, "via": via,
            "score": round(float(r["rank_weight"]), 3),
            "snippet": snippet_row["gloss"] if snippet_row else None,
        })

    # 1) Direct pass — the accent/case/sigma-folded key (exact lemmas + inflected
    #    forms). The fold is intentionally case/accent-insensitive (so `αετος`
    #    finds `αετός`), but that collapses a common noun and a proper name onto one
    #    key (αετός 'eagle' vs Αετός a placename/surname). Ranking by surface weight
    #    alone then ordered them arbitrarily and often surfaced the rarer proper noun
    #    first. We break the tie with two signals, in order:
    #      1. EXACT surface match against the raw query — typing `αετός` (lowercase)
    #         wants the bird; typing `Αετός` wants the name. The string the user
    #         actually wrote is the strongest disambiguator we have.
    #      2. corpus FREQUENCY — when neither is an exact-case hit (e.g. the user
    #         typed unaccented `αετος`), the more common lemma is the safer default.
    #    rank_weight (lemma > inflected form) and lemma_id keep it deterministic.
    raw = q.strip()
    for r in conn.execute(
        """
        SELECT si.lemma_id, si.surface, si.surface_type, si.features, si.rank_weight,
               l.lemma, l.pos, l.gender,
               COALESCE(fr.rank, 1000000000) AS freq_rank
        FROM search_index si JOIN lemmas l ON l.id = si.lemma_id
        LEFT JOIN frequency fr ON fr.lemma_id = si.lemma_id
        WHERE si.normalized_surface = ?
        ORDER BY (si.surface = ?) DESC, freq_rank ASC, si.rank_weight DESC, si.lemma_id ASC
        """,
        (key, raw),
    ).fetchall():
        if len(results) >= limit:
            break
        _emit(r, "direct")

    # 2) Greeklish fan-out — a single Latin spelling is ambiguous (i→ι/η/υ,
    #    o→ο/ω, e→ε/αι…), so we enumerate plausible Greek spellings and probe them
    #    all at once, ranked GLOBALLY by lemma frequency. This surfaces the common
    #    word the user meant (γη, ζωή) instead of whichever arm was generated first.
    if len(results) < limit:
        cand_keys: list[str] = []
        ck_seen: set[str] = {key}
        for c in greeklish_candidates(q):
            ck = normalize(c)
            if ck and ck not in ck_seen:
                ck_seen.add(ck)
                cand_keys.append(ck)
        if cand_keys:
            qmarks = ",".join("?" * len(cand_keys))
            for r in conn.execute(
                f"""
                SELECT si.lemma_id, si.surface, si.surface_type, si.features, si.rank_weight,
                       l.lemma, l.pos, l.gender,
                       COALESCE(fr.rank, 1000000000) AS freq_rank
                FROM search_index si JOIN lemmas l ON l.id = si.lemma_id
                LEFT JOIN frequency fr ON fr.lemma_id = si.lemma_id
                WHERE si.normalized_surface IN ({qmarks})
                ORDER BY freq_rank ASC, si.rank_weight DESC
                """,
                cand_keys,
            ).fetchall():
                if len(results) >= limit:
                    break
                _emit(r, "greeklish")

    # 3) Cross-language en→el (#39) — type an English word, land on the Greek
    #    lemma. A Latin query rarely resolves via the Greek index or greeklish
    #    (e.g. "eagle" → εαγλε… is nonsense), so we look the normalized English key
    #    up in `gloss_index` and rank the lemmas it translates by frequency. Only a
    #    lookup aid: the Greek dictionary stays primary, hence this runs last.
    if len(results) < limit:
        en_key = _en_key(q)
        if en_key:
            for r in conn.execute(
                """
                SELECT gi.lemma_id, gi.en_term, gi.rank_weight,
                       l.lemma AS lemma, l.pos, l.gender,
                       NULL AS surface, 'lemma' AS surface_type, NULL AS features,
                       COALESCE(fr.rank, 1000000000) AS freq_rank
                FROM gloss_index gi JOIN lemmas l ON l.id = gi.lemma_id
                LEFT JOIN frequency fr ON fr.lemma_id = gi.lemma_id
                WHERE gi.en_term = ?
                ORDER BY gi.rank_weight DESC, freq_rank ASC
                """,
                (en_key,),
            ).fetchall():
                if len(results) >= limit:
                    break
                _emit(r, "translation", en_term=r["en_term"])

    # Data flywheel: record the lookup. Best-effort — logging must never break
    # search, so any failure (locked DB, etc.) is swallowed.
    try:
        conn.execute(
            "INSERT INTO query_log (query, normalized, resolved, top_lemma_id, result_count, via) "
            "VALUES (?,?,?,?,?,?)",
            (
                q,
                key,
                1 if results else 0,
                results[0]["lemma_id"] if results else None,
                len(results),
                results[0]["via"] if results else None,
            ),
        )
        conn.commit()
    except sqlite3.Error:
        pass

    conn.close()
    return {"query": q, "normalized": key, "resolved": bool(results), "results": results}


@app.get("/api/word/{lemma}")
def word(lemma: str):
    """Full word-page payload for a lemma (accent-insensitive lookup)."""
    conn = db()
    lemma_ids = _resolve_lemma_ids(conn, lemma)
    if not lemma_ids:
        conn.close()
        raise HTTPException(404, f"No lemma for '{lemma}'.")
    qmarks = ",".join("?" * len(lemma_ids))
    lrows = conn.execute(
        f"SELECT * FROM lemmas WHERE id IN ({qmarks})", lemma_ids
    ).fetchall()
    # Preserve resolver priority order (SQL IN doesn't guarantee it).
    order = {lid: i for i, lid in enumerate(lemma_ids)}
    lrows = sorted(lrows, key=lambda r: order.get(r["id"], 1_000_000))

    payloads = []
    for l in lrows:
        senses = conn.execute(
            "SELECT sense_index, gloss, tags, examples, source FROM senses WHERE lemma_id = ? ORDER BY sense_index",
            (l["id"],),
        ).fetchall()
        forms = conn.execute(
            "SELECT form, features, source FROM forms WHERE lemma_id = ? ORDER BY id", (l["id"],)
        ).fetchall()
        ety = conn.execute(
            "SELECT text, source FROM etymology WHERE lemma_id = ?", (l["id"],)
        ).fetchone()
        etymons = conn.execute(
            "SELECT relation, lang_code, term, source FROM etymons WHERE lemma_id = ? ORDER BY seq",
            (l["id"],),
        ).fetchall()
        # Cognate cross-links ("ομόρριζες λέξεις"): OTHER Modern-Greek lemmas that
        # descend from one of THIS lemma's etymological ancestors (shared lang_code +
        # term). Ranked by ancestor SPECIFICITY — the fewer lemmas a root is shared
        # by, the closer the kinship — so tight families (grc λόγος → λογικός,
        # λογογράφος) surface ahead of broad ones. Mega-clusters (a generic PIE root
        # shared by 60+ words) are skipped: they'd be noise, not a useful cross-link.
        cognates: list[dict] = []
        sib: dict[str, tuple[str, str | None, str, int]] = {}  # name → (root, lang, source, group_size)
        for e in etymons:
            if not e["term"] or not e["lang_code"]:
                continue
            shares = conn.execute(
                "SELECT DISTINCT lm.lemma FROM etymons et JOIN lemmas lm ON lm.id = et.lemma_id "
                "WHERE et.lang_code = ? AND et.term = ? AND et.lemma_id != ?",
                (e["lang_code"], e["term"], l["id"]),
            ).fetchall()
            gsize = len(shares)
            if gsize == 0 or gsize > 60:
                continue
            for sr in shares:
                name = sr["lemma"]
                if name == l["lemma"]:
                    continue
                cur = sib.get(name)
                if cur is None or gsize < cur[3]:
                    sib[name] = (e["term"], e["lang_code"], e["source"], gsize)
        # closest (smallest group) first, then alphabetical; cap the panel
        for name, (root, lang, src, gsize) in sorted(sib.items(), key=lambda kv: (kv[1][3], kv[0]))[:12]:
            cognates.append({"term": name, "shared_root": root, "shared_lang": lang,
                             "resolved": True, "source": src})
        prons = conn.execute(
            "SELECT ipa, source FROM pronunciations WHERE lemma_id = ? ORDER BY seq",
            (l["id"],),
        ).fetchall()
        # Word family: typed lexical relations already captured at ingest, grouped
        # by relation_type and surfaced as a readable list (the graph shows the same
        # edges visually). Resolved targets carry the canonical lemma for linking.
        famrows = conn.execute(
            """
            SELECT r.relation_type, r.target_text, r.target_lemma_id, r.source, tl.lemma AS target_lemma
            FROM relations r LEFT JOIN lemmas tl ON tl.id = r.target_lemma_id
            WHERE r.source_lemma_id = ? ORDER BY r.relation_type, r.id
            """,
            (l["id"],),
        ).fetchall()
        family: dict[str, list] = {}
        fam_seen: set[tuple[str, str]] = set()
        for fr in famrows:
            term = fr["target_lemma"] or fr["target_text"]
            if not term or term == l["lemma"]:
                continue
            key = (fr["relation_type"], term)
            if key in fam_seen:
                continue
            fam_seen.add(key)
            family.setdefault(fr["relation_type"], []).append({
                "term": term,
                "resolved": fr["target_lemma_id"] is not None,
                "source": fr["source"],
            })
        # Descendants: cross-language words formed from this lemma (forward etymology).
        descrows = conn.execute(
            "SELECT relation, lang_code, lang_name, term, roman, source FROM descendants "
            "WHERE lemma_id = ? ORDER BY seq",
            (l["id"],),
        ).fetchall()
        freq = conn.execute(
            "SELECT count, rank, zipf, band, source FROM frequency WHERE lemma_id = ?",
            (l["id"],),
        ).fetchone()
        # Collocations: words that statistically co-occur with this lemma in a corpus.
        collocrows = conn.execute(
            "SELECT collocate, collocate_lemma_id, score, source FROM collocations "
            "WHERE lemma_id = ? ORDER BY seq",
            (l["id"],),
        ).fetchall()
        # KWIC examples: authentic corpus sentences using this lemma (ranked, best first).
        examplerows = conn.execute(
            "SELECT sentence, source FROM corpus_examples WHERE lemma_id = ? ORDER BY seq",
            (l["id"],),
        ).fetchall()
        # Semantic neighbors: distributional near-synonyms from a word-embedding model.
        neighborrows = conn.execute(
            "SELECT neighbor, neighbor_lemma_id, score, source FROM semantic_neighbors "
            "WHERE lemma_id = ? ORDER BY seq",
            (l["id"],),
        ).fetchall()
        payloads.append({
            "lemma_id": l["id"],
            "lemma": l["lemma"],
            "pos": l["pos"],
            "gender": l["gender"],
            "sources": (l["sources"] or "").split(","),
            "pronunciations": [{"ipa": p["ipa"], "source": p["source"]} for p in prons],
            "family": [
                {"relation": rel, "terms": terms} for rel, terms in family.items()
            ],
            "descendants": [
                {"relation": d["relation"], "lang": d["lang_code"], "lang_name": d["lang_name"],
                 "term": d["term"], "roman": d["roman"], "source": d["source"]}
                for d in descrows
            ],
            "cognates": cognates,
            "frequency": (
                {"count": freq["count"], "rank": freq["rank"], "zipf": freq["zipf"],
                 "band": freq["band"], "source": freq["source"]}
                if freq else None
            ),
            "collocations": [
                {"collocate": c["collocate"], "collocate_lemma_id": c["collocate_lemma_id"],
                 "score": c["score"], "source": c["source"]}
                for c in collocrows
            ],
            "examples": [
                {"sentence": e["sentence"], "source": e["source"]} for e in examplerows
            ],
            "neighbors": [
                {"neighbor": n["neighbor"], "neighbor_lemma_id": n["neighbor_lemma_id"],
                 "score": n["score"], "source": n["source"]}
                for n in neighborrows
            ],
            "senses": [
                {
                    "index": s["sense_index"],
                    "gloss": s["gloss"],
                    "tags": json.loads(s["tags"] or "[]"),
                    "examples": json.loads(s["examples"] or "[]"),
                    "source": s["source"],
                }
                for s in senses
            ],
            "forms": [
                {"form": f["form"], "features": json.loads(f["features"] or "[]"), "source": f["source"]}
                for f in forms
            ],
            "etymology": {"text": ety["text"], "source": ety["source"]} if ety and ety["text"] else None,
            "etymons": [
                {"relation": e["relation"], "lang": e["lang_code"], "term": e["term"], "source": e["source"]}
                for e in etymons
            ],
        })
    conn.close()
    return {"lemma": lemma, "entries": payloads}


@app.get("/api/word/{lemma}/graph")
def word_graph(lemma: str):
    """Minimal graph payload (M0 stub): explicit relations from the store.

    Real semantic neighbours (WordNet, embeddings) land in M4. For now this
    returns whatever typed relations ingest captured, so the frontend graph
    component can be built against a stable shape.
    """
    conn = db()
    lemma_ids = _resolve_lemma_ids(conn, lemma)
    if not lemma_ids:
        conn.close()
        raise HTTPException(404, f"No lemma for '{lemma}'.")
    lrow = conn.execute("SELECT id, lemma FROM lemmas WHERE id = ?", (lemma_ids[0],)).fetchone()
    # The 'related' catch-all dominates the table (~186k rows) and would, under a
    # bare LIMIT, crowd out the information-dense typed edges (synonym/antonym and
    # the WordNet taxonomy hypernym/hyponym). Rank the meaningful types first so a
    # high-degree node still shows its taxonomy, then fill remaining slots with
    # 'related'. Resolved (clickable) targets are preferred within a type.
    rels = conn.execute(
        """
        SELECT r.target_text, r.target_lemma_id, r.relation_type, r.weight, r.source, tl.lemma AS target_lemma
        FROM relations r LEFT JOIN lemmas tl ON tl.id = r.target_lemma_id
        WHERE r.source_lemma_id = ?
        ORDER BY CASE r.relation_type
            WHEN 'synonym' THEN 0 WHEN 'antonym' THEN 1
            WHEN 'hypernym' THEN 2 WHEN 'hyponym' THEN 3
            WHEN 'derived' THEN 4 ELSE 5 END,
          (r.target_lemma_id IS NULL), r.weight DESC, r.id
        LIMIT 60
        """,
        (lrow["id"],),
    ).fetchall()
    nodes = {lrow["lemma"]: {"id": lrow["lemma"], "label": lrow["lemma"], "type": "current", "resolved": True, "lemma_id": lrow["id"]}}
    edges = []
    edge_seen: set[tuple[str, str]] = set()  # collapse parallel (target,type) edges from multiple sources
    for r in rels:
        # Prefer the canonical lemma display for resolved targets so multiple
        # relations to the same word collapse onto one clickable node.
        node_id = r["target_lemma"] or r["target_text"]
        if not node_id:
            continue
        ekey = (node_id, r["relation_type"])
        if ekey in edge_seen:
            continue
        edge_seen.add(ekey)
        resolved = r["target_lemma_id"] is not None
        if node_id not in nodes:
            nodes[node_id] = {
                "id": node_id, "label": node_id, "type": r["relation_type"],
                "resolved": resolved, "lemma_id": r["target_lemma_id"],
            }
        edges.append({
            "source": lrow["lemma"], "target": node_id,
            "type": r["relation_type"], "weight": r["weight"], "source_name": r["source"],
        })

    # Etymological origins: cross-language ancestors (grc, ine-pro, la…). They are
    # not Modern-Greek lemmas, so they read as unresolved (non-clickable) nodes
    # tagged with their source language. Same typed+sourced edge contract.
    etymons = conn.execute(
        "SELECT relation, lang_code, term, source FROM etymons WHERE lemma_id = ? ORDER BY seq LIMIT 20",
        (lrow["id"],),
    ).fetchall()
    # Render the chain as a LINEAGE PATH, not a flat star: each step links to the
    # PREVIOUS one (headword → grc-koi Ἰανουάριος → la ianuarius → ine-pro *yeh₂-),
    # so the graph shows true diachronic depth. `seq` (ORDER BY above) gives the
    # order; each edge's relation describes how that term relates to its parent.
    prev_node = lrow["lemma"]
    for e in etymons:
        node_id = f"{e['term']} ({e['lang_code']})" if e["lang_code"] else e["term"]
        if node_id not in nodes:
            nodes[node_id] = {
                "id": node_id, "label": e["term"], "type": e["relation"],
                "resolved": False, "lemma_id": None, "etymon": True, "lang": e["lang_code"],
            }
        edges.append({
            "source": prev_node, "target": node_id,
            "type": e["relation"], "weight": 1.0, "source_name": e["source"],
        })
        prev_node = node_id

    conn.close()
    return {"nodes": list(nodes.values()), "edges": edges}


@app.get("/api/attributions")
def attributions():
    """CC BY-SA / GFDL source attribution registry (one row per data source).

    Surfaced centrally in the UI (site footer + /licensing) to satisfy the
    Wiktionary attribution + ShareAlike requirement without scattering the full
    legal notice onto every term — provenance per item is already carried by the
    `source` badges.
    """
    conn = db()
    rows = conn.execute(
        "SELECT source_name, source_url, license, attribution_text, retrieved_at "
        "FROM source_attributions ORDER BY source_name"
    ).fetchall()
    conn.close()
    return {"attributions": [dict(r) for r in rows]}


@app.get("/api/insights/queries")
def query_insights(limit: int = 50):
    """Data-flywheel readout from the query log: volume, resolution rate, and the
    top UNRESOLVED queries — the gap list of words users want that we don't serve.
    These rank what to ingest next and seed spell-correction."""
    conn = db()
    totals = conn.execute(
        "SELECT COUNT(*) AS total, "
        "SUM(CASE WHEN resolved = 0 THEN 1 ELSE 0 END) AS unresolved "
        "FROM query_log"
    ).fetchone()
    top_unresolved = conn.execute(
        "SELECT normalized, COUNT(*) AS hits, MAX(query) AS sample "
        "FROM query_log WHERE resolved = 0 AND normalized != '' "
        "GROUP BY normalized ORDER BY hits DESC, normalized LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    total = totals["total"] or 0
    unresolved = totals["unresolved"] or 0
    return {
        "total_queries": total,
        "unresolved_queries": unresolved,
        "resolution_rate": round(1 - unresolved / total, 4) if total else None,
        "top_unresolved": [
            {"normalized": r["normalized"], "sample": r["sample"], "hits": r["hits"]}
            for r in top_unresolved
        ],
    }


# Greek function words / particles whose drift scores are noise (unstable vectors,
# not meaning change). Used only to clean the "biggest movers" discovery list — the
# per-word diachronic payload still returns a score for any lemma the user visits.
_DRIFT_STOP = {
    "και", "κι", "που", "πως", "για", "δεν", "δε", "θα", "να", "αλλα", "ομως",
    "ενω", "οτι", "οταν", "οπως", "οσο", "γιατι", "επειδη", "ωστε", "αρα", "λοιπον",
    "ειναι", "ηταν", "εχει", "εχουν", "ειχε", "καθε", "καποιος", "καποια", "καποιο",
    "αυτος", "αυτη", "αυτο", "αυτοι", "αυτες", "αυτα", "εκεινος", "τους", "της",
    "των", "τον", "την", "στο", "στη", "στον", "στην", "στις", "στους", "στα",
    "απο", "προς", "κατα", "μετα", "πριν", "χωρις", "παρα", "μεσα", "εξω", "πανω",
    "κατω", "διοτι", "μηπως", "ισως", "πολυ", "παρα", "μονο", "ηδη", "ακομα",
    "ακομη", "τοτε", "τωρα", "εδω", "εκει", "οπου", "καθως", "παν", "χαριν",
}

# Display order of corpora in the diachronic UI: Parliament is the deep primary
# axis (true dates, single register), news is the parallel secondary line, and any
# further corpora (wiki/web/literature) follow — each its own axis, never merged.
_CORPUS_ORDER = {"parliament": 0, "news": 1, "wiki": 2, "web": 3, "literature": 4, "mixed": 5}

# Content parts of speech for the discovery/exploration lists: only nouns,
# adjectives and verbs. Proper nouns ('name'), adverbs and function words drift
# noisily or churn with current events rather than changing meaning.
_CONTENT_POS = ("noun", "adj", "verb")

# Subject fields surfaced on the exploration "by field" section. Keys match the
# English domain tags stored in senses.tags / topics; the frontend maps them to
# Greek via labels.domainEl. Kept to broad, well-populated fields so each column
# has enough movers to be interesting.
_FIELD_DOMAINS = [
    "medicine", "law", "politics", "economics", "computing", "technology",
    "military", "religion", "philosophy", "music", "sports", "physics",
    "chemistry", "biology", "mathematics", "history", "linguistics", "nautical",
]

# Process-lifetime memo for the expensive cross-row aggregations (neighbor
# overlap, lemma→domain map). Cleared on restart; the discovery page is read-only
# so a stale-after-write cache is acceptable (a re-ingest restarts the API anyway).
_EXPLORE_CACHE: dict = {}


def _keep_mover(lemma: str, normalized_lemma: str) -> bool:
    """Shared noise filter for every discovery list: drop function words and
    proper nouns (capitalized initial — names/places churn, not meaning change)."""
    if normalized_lemma in _DRIFT_STOP:
        return False
    if lemma[:1].isupper():
        return False
    return True


def _endpoint_pm(conn, corpus: str, lemma_id: int, year: int):
    row = conn.execute(
        "SELECT per_million FROM frequency_timeseries WHERE lemma_id=? AND corpus=? AND year=?",
        (lemma_id, corpus, year),
    ).fetchone()
    return row["per_million"] if row else None


# ── Materialized cache for the expensive, deterministic explore endpoints ──────
# trends/compare recompute the same answer every call (pure functions of the
# Layer-B/C tables) and cost 20–35 s. We persist their JSON in `explore_cache`,
# fingerprinted by a cheap signature of the source-row counts. A re-ingest changes
# the counts → the signature no longer matches → the next request recomputes and
# refreshes. No pipeline coupling; the cache is self-healing and write-through.
def _data_sig(conn) -> str:
    d = conn.execute("SELECT COUNT(*) FROM diachronic_drift").fetchone()[0]
    t = conn.execute("SELECT COUNT(*) FROM frequency_timeseries").fetchone()[0]
    return f"drift={d};ts={t}"


def _bh_fdr(p_by_id: dict[int, float], alpha: float = 0.05):
    """Benjamini–Hochberg FDR over {id: raw_p} → ({id: q_value}, {id: reject}).
    `q_value` is the monotone step-up-adjusted p; `reject` is the decision at `alpha`.
    Bounds the false-discovery proportion across the many lemmas tested at once."""
    ids = list(p_by_id)
    m = len(ids)
    if m == 0:
        return {}, {}
    order = sorted(ids, key=lambda i: p_by_id[i])
    q: dict[int, float] = {}
    prev = 1.0
    # Walk from the largest p down, taking the running minimum of p·m/rank (the
    # standard BH step-up adjustment) so q-values stay monotone in p.
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        prev = min(prev, p_by_id[i] * m / rank)
        q[i] = min(prev, 1.0)
    reject = {i: q[i] <= alpha for i in ids}
    return q, reject


def _theil_sen_slope(years: list[int], vals: list[float]) -> float:
    """Theil–Sen slope: median of all pairwise (Δvalue/Δyear) slopes — robust to a
    single outlier year, unlike OLS. Used as the displayed per-million change/year."""
    slopes: list[float] = []
    n = len(years)
    for i in range(n - 1):
        yi, vi = years[i], vals[i]
        for j in range(i + 1, n):
            dt = years[j] - yi
            if dt:
                slopes.append((vals[j] - vi) / dt)
    if not slopes:
        return 0.0
    slopes.sort()
    m = len(slopes)
    return slopes[m // 2] if m % 2 else 0.5 * (slopes[m // 2 - 1] + slopes[m // 2])


def _mann_kendall_p(vals: list[float]) -> tuple[float, int]:
    """Two-sided Mann–Kendall trend p-value (tie-corrected normal approximation),
    on values already ordered by year. Non-parametric, so no linearity/normality
    assumption. It does assume independent years; our series are short (11–31 points)
    and serially correlated, so p is approximate — we lean on the R² shape gate and
    BH-FDR rather than on this p alone. Returns (p, S)."""
    import numpy as np
    from scipy.stats import norm as _norm

    n = len(vals)
    if n < 4:
        return 1.0, 0
    x = np.asarray(vals, dtype=float)
    s = 0
    for k in range(n - 1):
        s += int(np.sign(x[k + 1:] - x[k]).sum())
    _, counts = np.unique(x, return_counts=True)
    var_s = (n * (n - 1) * (2 * n + 5)
             - float(np.sum(counts * (counts - 1) * (2 * counts + 5)))) / 18.0
    if var_s <= 0:
        return 1.0, s
    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0
    return min(float(2.0 * _norm.sf(abs(z))), 1.0), s


def _log_likelihood_g2(a: int, b: int, c: int, d: int) -> float:
    """Dunning (1993) log-likelihood G² for freq `a` in corpus 1 (size `c`) vs `b` in
    corpus 2 (size `d`): the keyness significance statistic, ~χ²₁ (>10.83 ↔ p<0.001).
    Direction comes from the log ratio; G² is the strength of evidence. ≥0; 0 if a/c=b/d."""
    if a + b == 0:
        return 0.0
    e1 = c * (a + b) / (c + d)
    e2 = d * (a + b) / (c + d)
    g2 = 0.0
    if a > 0 and e1 > 0:
        g2 += a * math.log(a / e1)
    if b > 0 and e2 > 0:
        g2 += b * math.log(b / e2)
    return 2.0 * g2


def _hardie_log_ratio(a: int, b: int, c: int, d: int):
    """Hardie (2014) Log Ratio (effect size) + 95% CI: log₂ of (a/c)/(b/d), +1 = twice
    as common in corpus 1. CI from the delta-method variance of the log relative risk
    (1/a−1/c+1/b−1/d), rescaled to log₂. Callers pass a,b>0. Returns (lr, ci_lo, ci_hi)."""
    if a <= 0 or b <= 0 or c <= 0 or d <= 0:
        return 0.0, 0.0, 0.0
    lr = math.log2((a / c) / (b / d))
    var = 1.0 / a + 1.0 / b - 1.0 / c - 1.0 / d
    se = (math.sqrt(var) / math.log(2)) if var > 0 else 0.0
    return lr, lr - 1.96 * se, lr + 1.96 * se


def _cache_get(conn, key: str):
    """Return the cached payload for `key` iff it matches the current data
    signature, else None (caller should recompute)."""
    row = conn.execute(
        "SELECT sig, payload FROM explore_cache WHERE cache_key=?", (key,)
    ).fetchone()
    if row and row["sig"] == _data_sig(conn):
        try:
            return json.loads(row["payload"])
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _cache_put(conn, key: str, payload: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO explore_cache (cache_key, sig, payload, built_at) "
        "VALUES (?, ?, ?, ?)",
        (key, _data_sig(conn), json.dumps(payload, ensure_ascii=False),
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


@app.get("/api/word/{lemma}/diachronic")
def word_diachronic(lemma: str):
    """Diachronic payload for a word page: per-corpus frequency-over-time plus the
    semantic-drift score and 'then vs now' neighbor lists. Corpora are returned as
    SEPARATE labeled series and never merged — a time series is only valid within
    one consistent corpus. Returns empty series for words with no diachronic data."""
    conn = db()
    lemma_ids = _resolve_lemma_ids(conn, lemma)
    if not lemma_ids:
        conn.close()
        raise HTTPException(404, f"No lemma for '{lemma}'.")
    lid = lemma_ids[0]
    lrow = conn.execute("SELECT lemma FROM lemmas WHERE id = ?", (lid,)).fetchone()

    corpora = [r["corpus"] for r in conn.execute(
        "SELECT DISTINCT corpus FROM frequency_timeseries WHERE lemma_id = ? "
        "UNION SELECT DISTINCT corpus FROM diachronic_drift WHERE lemma_id = ? "
        "UNION SELECT DISTINCT corpus FROM diachronic_neighbors WHERE lemma_id = ?",
        (lid, lid, lid),
    )]
    corpora.sort(key=lambda c: _CORPUS_ORDER.get(c, 99))

    def _neighbors(corpus: str, year: int) -> list[dict]:
        return [
            {"neighbor": n["neighbor"], "neighbor_lemma_id": n["neighbor_lemma_id"],
             "score": n["score"]}
            for n in conn.execute(
                "SELECT neighbor, neighbor_lemma_id, score FROM diachronic_neighbors "
                "WHERE lemma_id = ? AND corpus = ? AND year = ? ORDER BY seq",
                (lid, corpus, year),
            )
        ]

    series = []
    for corpus in corpora:
        freq = [
            {"year": r["year"], "per_million": r["per_million"], "count": r["count"]}
            for r in conn.execute(
                "SELECT year, per_million, count FROM frequency_timeseries "
                "WHERE lemma_id = ? AND corpus = ? ORDER BY year",
                (lid, corpus),
            )
        ]
        drow = conn.execute(
            "SELECT drift_score, drift_score_boot, first_year, last_year, n_slices, "
            "change_point_year, change_point_score, drift_ci_lo, drift_ci_hi, "
            "drift_significant, drift_q "
            "FROM diachronic_drift WHERE lemma_id = ? AND corpus = ?",
            (lid, corpus),
        ).fetchone()
        drift = (
            # One coherent point estimate: the bootstrap mean when available (centre of
            # the CI, #50), else the single-model score until bootstrap has run. The
            # internal extras (single/boot/q) are not surfaced — the UI shows score, CI,
            # significance, and the change point.
            {"drift_score": (drow["drift_score_boot"] if drow["drift_score_boot"] is not None
                             else drow["drift_score"]),
             "first_year": drow["first_year"],
             "last_year": drow["last_year"], "n_slices": drow["n_slices"],
             "change_point_year": drow["change_point_year"],
             "change_point_score": drow["change_point_score"],
             "drift_ci_lo": drow["drift_ci_lo"], "drift_ci_hi": drow["drift_ci_hi"],
             "drift_significant": (
                 None if drow["drift_significant"] is None
                 else bool(drow["drift_significant"]))}
            if drow else None
        )
        # Full per-slice trajectory (#35): the SHAPE of change, not just endpoints.
        trajectory = [
            {"year": t["year"], "distance_from_ref": t["distance_from_ref"]}
            for t in conn.execute(
                "SELECT year, distance_from_ref FROM diachronic_trajectory "
                "WHERE lemma_id = ? AND corpus = ? ORDER BY year",
                (lid, corpus),
            )
        ]
        # 'then' / 'now' = earliest / latest year with stored era-neighbors.
        nyears = [r["year"] for r in conn.execute(
            "SELECT DISTINCT year FROM diachronic_neighbors WHERE lemma_id = ? AND corpus = ? "
            "ORDER BY year", (lid, corpus),
        )]
        neighbors_then = (
            {"year": nyears[0], "items": _neighbors(corpus, nyears[0])} if nyears else None
        )
        neighbors_now = (
            {"year": nyears[-1], "items": _neighbors(corpus, nyears[-1])}
            if len(nyears) > 1 else None
        )
        series.append({
            "corpus": corpus,
            "frequency": freq,
            "drift": drift,
            "trajectory": trajectory,
            "neighbors_then": neighbors_then,
            "neighbors_now": neighbors_now,
        })

    conn.close()
    return {"lemma": lrow["lemma"], "lemma_id": lid, "series": series}


@app.get("/api/insights/drift")
def drift_insights(corpus: str = "parliament", limit: int = 30, min_pm: float = 1.0):
    """'Biggest movers' — lemmas whose meaning shifted most within one corpus.

    The raw drift table keeps every lemma (a word page needs its own score), but
    this discovery list filters the noise: function words / particles with unstable
    vectors are dropped, very short tokens excluded, lemmas sharing a normalized
    surface are collapsed (so 'ε/Ε/ε' don't flood the list), and only content words
    (nouns / adjectives / verbs) are kept — adverbs drift noisily and proper nouns
    ('name' POS) churn with current events rather than changing meaning.

    Cosine drift is frequency-confounded (Dubossarsky et al. 2017): a rare word's
    vector is poorly estimated and looks like a big mover. We therefore apply the
    same per-million floor in BOTH anchor years that /explore/interesting uses, so
    'biggest movers' is the frequency-robust list, consistent with §3."""
    conn = db()
    rows = conn.execute(
        """
        SELECT l.lemma, l.normalized_lemma, d.lemma_id, MAX(d.drift_score) AS drift,
               d.first_year, d.last_year
        FROM diachronic_drift d JOIN lemmas l ON l.id = d.lemma_id
        JOIN frequency_timeseries f0
          ON f0.lemma_id = d.lemma_id AND f0.corpus = d.corpus
         AND f0.year = d.first_year AND f0.per_million >= ?
        JOIN frequency_timeseries f1
          ON f1.lemma_id = d.lemma_id AND f1.corpus = d.corpus
         AND f1.year = d.last_year AND f1.per_million >= ?
        WHERE d.corpus = ? AND LENGTH(l.normalized_lemma) >= 4
          AND l.pos IN ('noun', 'adj', 'verb')
        GROUP BY l.normalized_lemma
        ORDER BY drift DESC
        LIMIT ?
        """,
        (min_pm, min_pm, corpus, max(limit * 4, 120)),
    ).fetchall()
    conn.close()
    movers = []
    for r in rows:
        if r["normalized_lemma"] in _DRIFT_STOP:
            continue
        # Proper nouns (names of people/places) drift hard simply because the
        # individuals/events in the news churn year to year — that's not meaning
        # change, so drop capitalized-initial lemmas from the discovery list.
        if r["lemma"][:1].isupper():
            continue
        movers.append({
            "lemma": r["lemma"],
            "lemma_id": r["lemma_id"],
            "drift_score": r["drift"],
            "first_year": r["first_year"],
            "last_year": r["last_year"],
        })
        if len(movers) >= limit:
            break
    return {"corpus": corpus, "movers": movers}


# ───────────────────────── Exploration page (/explore) ─────────────────────────
# A discovery surface over the diachronic layers. Every section keeps the corpora
# on SEPARATE axes (cardinal rule); the only place they meet is /explore/compare,
# which is explicitly a *comparison*. All sections run over existing tables — no
# embedding retraining — using literature-backed change measures:
#   · cosine drift            — Hamilton, Leskovec & Jurafsky 2016
#   · neighbor-overlap drift  — Gonen et al. 2020 (frequency-robust, interpretable)
#   · frequency-gating        — controls the Dubossarsky et al. 2017 frequency bias
#   · keyness (log-ratio)     — corpus-linguistics distinctiveness (Kilgarriff 2009)


@app.get("/api/explore/overview")
def explore_overview():
    """Cumulative corpus view: tokens & vocabulary per year, per corpus. Frames
    the two axes side by side (and honestly shows why they can't be merged — wildly
    different sizes and eras)."""
    conn = db()
    corpora = [r[0] for r in conn.execute(
        "SELECT DISTINCT corpus FROM frequency_timeseries").fetchall()]
    corpora.sort(key=lambda c: _CORPUS_ORDER.get(c, 99))
    out = []
    for c in corpora:
        rows = conn.execute(
            "SELECT year, SUM(count) AS tokens, COUNT(*) AS types "
            "FROM frequency_timeseries WHERE corpus=? GROUP BY year ORDER BY year",
            (c,),
        ).fetchall()
        points = [{"year": r["year"], "tokens": r["tokens"], "types": r["types"]} for r in rows]
        drift_n = conn.execute(
            "SELECT COUNT(*) FROM diachronic_drift WHERE corpus=?", (c,)).fetchone()[0]
        out.append({
            "corpus": c,
            "points": points,
            "total_tokens": sum(p["tokens"] for p in points),
            "n_slices": len(points),
            "first_year": points[0]["year"] if points else None,
            "last_year": points[-1]["year"] if points else None,
            "drift_lemmas": drift_n,
        })
    conn.close()
    return {"corpora": out}


@app.get("/api/explore/interesting")
def explore_interesting(corpus: str = "parliament", limit: int = 25, min_pm: float = 1.0):
    """Frequency-robust 'interesting movers', two metrics side by side:
      · neighbor — 1 − Jaccard of a word's top-k neighbors then vs now (Gonen 2020),
        precomputed at k=50 in the pipeline and stored on diachronic_drift; far more
        stable than cosine and interpretable ("it left X's company, joined Y's").
      · freq_gated — cosine drift, but the word must clear `min_pm` per-million in
        BOTH anchor years (controls the frequency artifact; Dubossarsky 2017).
    Both lists are content-words only, deduped by normalized surface."""
    conn = db()

    # --- neighbor-overlap (Gonen 2020), read from the stored column ---
    # Same frequency gate as the cosine list (Dubossarsky 2017): without it the
    # change=1.0 ties are dominated by rare-word noise (50-neighbor sets that
    # simply never intersect). The avg_pm tiebreaker floats genuinely common,
    # high-turnover words to the top of the saturated band.
    nrows = conn.execute(
        """
        SELECT l.lemma, l.normalized_lemma, d.lemma_id,
               MAX(d.neighbor_overlap) AS change, d.first_year, d.last_year,
               (f0.per_million + f1.per_million) / 2.0 AS avg_pm
        FROM diachronic_drift d
        JOIN lemmas l ON l.id = d.lemma_id
        JOIN frequency_timeseries f0
          ON f0.lemma_id = d.lemma_id AND f0.corpus = d.corpus
         AND f0.year = d.first_year AND f0.per_million >= ?
        JOIN frequency_timeseries f1
          ON f1.lemma_id = d.lemma_id AND f1.corpus = d.corpus
         AND f1.year = d.last_year AND f1.per_million >= ?
        WHERE d.corpus = ? AND d.neighbor_overlap IS NOT NULL
          AND LENGTH(l.normalized_lemma) >= 4 AND l.pos IN ('noun', 'adj', 'verb')
        GROUP BY l.normalized_lemma
        ORDER BY change DESC, avg_pm DESC
        LIMIT ?
        """,
        (min_pm, min_pm, corpus, max(limit * 4, 120)),
    ).fetchall()
    neighbor = []
    for r in nrows:
        if not _keep_mover(r["lemma"], r["normalized_lemma"]):
            continue
        neighbor.append({
            "lemma": r["lemma"], "lemma_id": r["lemma_id"],
            "change": round(r["change"], 4),
            "first_year": r["first_year"], "last_year": r["last_year"],
        })
        if len(neighbor) >= limit:
            break

    # --- frequency-gated cosine drift ---
    rows = conn.execute(
        """
        SELECT l.lemma, l.normalized_lemma, d.lemma_id, MAX(d.drift_score) AS drift,
               d.first_year, d.last_year
        FROM diachronic_drift d
        JOIN lemmas l ON l.id = d.lemma_id
        JOIN frequency_timeseries f0
          ON f0.lemma_id = d.lemma_id AND f0.corpus = d.corpus
         AND f0.year = d.first_year AND f0.per_million >= ?
        JOIN frequency_timeseries f1
          ON f1.lemma_id = d.lemma_id AND f1.corpus = d.corpus
         AND f1.year = d.last_year AND f1.per_million >= ?
        WHERE d.corpus = ? AND LENGTH(l.normalized_lemma) >= 4
          AND l.pos IN ('noun', 'adj', 'verb')
        GROUP BY l.normalized_lemma
        ORDER BY drift DESC
        LIMIT ?
        """,
        (min_pm, min_pm, corpus, max(limit * 4, 120)),
    ).fetchall()
    freq_gated = []
    for r in rows:
        if not _keep_mover(r["lemma"], r["normalized_lemma"]):
            continue
        freq_gated.append({
            "lemma": r["lemma"], "lemma_id": r["lemma_id"],
            "drift_score": round(r["drift"], 4),
            "first_year": r["first_year"], "last_year": r["last_year"],
        })
        if len(freq_gated) >= limit:
            break
    conn.close()
    return {"corpus": corpus, "min_pm": min_pm, "neighbor": neighbor, "freq_gated": freq_gated}


# Classifier predictions below this confidence are hidden from the "ανά πεδίο"
# lists — a low-confidence guess is worse than no field at all. Gold (Wiktionary)
# tags carry score=1.0 and always pass. Display gate sits on top of the pipeline's
# coarser STORE_FLOOR, so it can be tightened here without re-running ingest (#38).
_DOMAIN_PRED_GATE = 0.55


def _lemma_domains(conn):
    """Map lemma_id → {domain: (source, score)} for the "ανά πεδίο" exploration.

    Reads the supervised `lemma_domain_pred` table (#38): gold Wiktionary tags
    (source='wiktionary-tag', score 1.0, always kept) plus classifier predictions
    (source='classifier') gated at _DOMAIN_PRED_GATE. If that table is empty (the
    classifier hasn't been run yet), falls back to the legacy senses.tags ∩
    _FIELD_DOMAINS heuristic so the endpoint degrades gracefully. Memoized."""
    if "domains" in _EXPLORE_CACHE:
        return _EXPLORE_CACHE["domains"]
    wanted = set(_FIELD_DOMAINS)
    out: dict = defaultdict(dict)

    has_pred = conn.execute(
        "SELECT 1 FROM lemma_domain_pred LIMIT 1"
    ).fetchone()
    if has_pred:
        for r in conn.execute(
            "SELECT lemma_id, domain, score, source FROM lemma_domain_pred"
        ):
            if r["domain"] not in wanted:
                continue
            if r["source"] == "classifier" and (r["score"] or 0) < _DOMAIN_PRED_GATE:
                continue
            # Gold wins over a classifier guess for the same lemma+domain.
            prev = out[r["lemma_id"]].get(r["domain"])
            if prev is None or (prev[0] != "wiktionary-tag" and r["source"] == "wiktionary-tag"):
                out[r["lemma_id"]][r["domain"]] = (r["source"], float(r["score"]))
    else:
        rows = conn.execute(
            "SELECT lemma_id, tags FROM senses "
            "WHERE tags IS NOT NULL AND tags != '' AND tags != '[]'"
        ).fetchall()
        for r in rows:
            try:
                tags = json.loads(r["tags"])
            except (ValueError, TypeError):
                continue
            for t in tags:
                tl = str(t).lower()
                if tl in wanted:
                    out[r["lemma_id"]][tl] = ("wiktionary-tag", 1.0)

    _EXPLORE_CACHE["domains"] = out
    return out


@app.get("/api/explore/by-field")
def explore_by_field(corpus: str = "parliament", per_field: int = 8):
    """Biggest movers WITHIN each subject field (ιατρική, νομική, πληροφορική …).
    Joins cosine drift with the sense domain tags. Field keys are English; the UI
    maps them to Greek."""
    conn = db()
    domains = _lemma_domains(conn)
    # Drift lookup for this corpus, plus lemma metadata for the candidates.
    drift = {}
    rows = conn.execute(
        "SELECT d.lemma_id, l.lemma, l.normalized_lemma, l.pos, d.drift_score, "
        "d.first_year, d.last_year FROM diachronic_drift d "
        "JOIN lemmas l ON l.id = d.lemma_id WHERE d.corpus = ?",
        (corpus,),
    ).fetchall()
    for r in rows:
        drift[r["lemma_id"]] = r

    fields = []
    for field in _FIELD_DOMAINS:
        movers = []
        seen: set = set()
        cands = []
        for lid, doms in domains.items():
            if field in doms and lid in drift:
                cands.append((drift[lid], doms[field]))  # (drift row, (source, score))
        cands.sort(key=lambda c: c[0]["drift_score"], reverse=True)
        for r, (dsource, dscore) in cands:
            if r["pos"] not in _CONTENT_POS or len(r["normalized_lemma"]) < 4:
                continue
            if not _keep_mover(r["lemma"], r["normalized_lemma"]) or r["normalized_lemma"] in seen:
                continue
            seen.add(r["normalized_lemma"])
            movers.append({
                "lemma": r["lemma"], "lemma_id": r["lemma_id"],
                "drift_score": round(r["drift_score"], 4),
                "first_year": r["first_year"], "last_year": r["last_year"],
                # #38 provenance: 'wiktionary-tag' (gold) vs 'classifier' (inferred).
                "domain_source": dsource,
                "domain_score": round(dscore, 4) if dscore is not None else None,
            })
            if len(movers) >= per_field:
                break
        if movers:
            # Share of this field's shown movers that are classifier-inferred —
            # lets the UI flag a column that leans heavily on prediction.
            inferred = sum(1 for m in movers if m["domain_source"] == "classifier")
            fields.append({
                "field": field, "movers": movers,
                "inferred_share": round(inferred / len(movers), 3),
            })
    # Most-populated / highest-drifting fields first.
    fields.sort(key=lambda f: f["movers"][0]["drift_score"], reverse=True)
    conn.close()
    return {"corpus": corpus, "fields": fields}


@app.get("/api/explore/trends")
def explore_trends(corpus: str = "parliament", limit: int = 20,
                   min_avg_pm: float = 1.0, min_r2: float = 0.25):
    """Cumulative-usage trend (Layer B): per-million linear slope over the corpus
    span. Risers (slope ↑) and fallers (slope ↓), content words only. Slope is the
    least-squares fit computed directly in SQL.

    A bare slope is misleading on a spiky series — one outlier year can fake a big
    trend. We also compute R² (the share of variance the linear fit explains) from
    the same aggregate sums and require min_r2, so only series with a genuinely
    linear rise/fall qualify. Sxy = n·Σxy − Σx·Σy, Sxx = n·Σx² − (Σx)²,
    Syy = n·Σy² − (Σy)²; slope = Sxy/Sxx, R² = Sxy²/(Sxx·Syy).

    Fully deterministic → served from `explore_cache` when warm (≈35 s recompute
    only on the first call after a re-ingest changes the data signature)."""
    conn = db()
    # v5 (#45): `slope` is the Theil–Sen slope and significance is the Mann–Kendall
    # p → BH-FDR (was OLS slope t-test); bump to discard older cached shapes.
    cache_key = f"trends:v5:{corpus}:{limit}:{min_avg_pm}:{min_r2}"
    cached = _cache_get(conn, cache_key)
    if cached is not None:
        conn.close()
        return cached
    n_years = conn.execute(
        "SELECT COUNT(DISTINCT year) FROM frequency_timeseries WHERE corpus=?", (corpus,)
    ).fetchone()[0]
    min_n = max(5, int(n_years * 0.5))  # #45: never test a trend on fewer than 5 years
    rows = conn.execute(
        """
        SELECT f.lemma_id, l.lemma, l.normalized_lemma, l.pos,
               COUNT(*) AS n, AVG(f.per_million) AS avg_pm,
               MIN(f.year) AS y0, MAX(f.year) AS y1,
               (COUNT(*) * SUM(f.year * f.per_million) - SUM(f.year) * SUM(f.per_million)) AS sxy,
               (COUNT(*) * SUM(f.year * f.year) - SUM(f.year) * SUM(f.year)) AS sxx,
               (COUNT(*) * SUM(f.per_million * f.per_million) - SUM(f.per_million) * SUM(f.per_million)) AS syy,
               (COUNT(*) * SUM(f.year * f.per_million) - SUM(f.year) * SUM(f.per_million)) /
               (COUNT(*) * SUM(f.year * f.year) - SUM(f.year) * SUM(f.year)) AS slope
        FROM frequency_timeseries f
        JOIN lemmas l ON l.id = f.lemma_id
        WHERE f.corpus = ? AND l.pos IN ('noun', 'adj', 'verb')
          AND LENGTH(l.normalized_lemma) >= 4
        GROUP BY f.lemma_id
        HAVING n >= ? AND avg_pm >= ?
           AND sxx > 0 AND syy > 0
           AND (sxy * sxy) / (sxx * syy) >= ?
        """,
        (corpus, min_n, min_avg_pm, min_r2),
    ).fetchall()
    cands = [r for r in rows if _keep_mover(r["lemma"], r["normalized_lemma"])]

    # Significance via Mann–Kendall, ranking via the robust Theil–Sen slope (#45),
    # replacing the OLS slope t-test (which assumed i.i.d. years). The SQL gates on
    # linear shape (R²), n≥min_n and avg_pm, so this runs on the gated set only.
    # Fetch each candidate's year→per-million series (chunked; SQLite caps params at 999).
    series_by_id: dict[int, list[tuple[int, float]]] = {}
    cand_ids = [r["lemma_id"] for r in cands]
    for off in range(0, len(cand_ids), 900):
        chunk = cand_ids[off:off + 900]
        qmarks = ",".join("?" * len(chunk))
        for row in conn.execute(
            f"SELECT lemma_id, year, per_million FROM frequency_timeseries "
            f"WHERE corpus=? AND lemma_id IN ({qmarks}) ORDER BY lemma_id, year",
            (corpus, *chunk),
        ):
            series_by_id.setdefault(row["lemma_id"], []).append(
                (row["year"], row["per_million"]))

    # Multiple-comparison control (#2): thousands of lemmas tested at once, so a raw
    # p<0.05 flag would admit ~5% of candidates as false "trends". Compute the MK p for
    # every candidate, then apply Benjamini–Hochberg FDR across the whole set; the
    # surfaced `significant` is the BH decision at q<0.05 (FDR, not Bonferroni — we want
    # a calibrated discovery rate, not to crush power on a genuinely trending vocabulary).
    p_by_id: dict[int, float] = {}
    r2_by_id: dict[int, float] = {}
    sen_by_id: dict[int, float] = {}
    for r in cands:
        lid = r["lemma_id"]
        r2_by_id[lid] = ((r["sxy"] * r["sxy"]) / (r["sxx"] * r["syy"])
                         if r["sxx"] and r["syy"] else 0.0)
        series = series_by_id.get(lid, [])
        yrs = [y for y, _ in series]
        pms = [p for _, p in series]
        sen_by_id[lid] = _theil_sen_slope(yrs, pms) if len(yrs) >= 2 else 0.0
        # min_n (≥5) already guarantees length; guard anyway so MK never sees a short series.
        p_by_id[lid] = _mann_kendall_p(pms)[0] if len(yrs) >= 5 else 1.0
    q_by_id, sig_by_id = _bh_fdr(p_by_id, alpha=0.05)

    def pack(r):
        lid = r["lemma_id"]
        return {
            "lemma": r["lemma"], "lemma_id": lid,
            "slope": round(sen_by_id[lid], 4), "avg_pm": round(r["avg_pm"], 2),
            "r2": round(r2_by_id[lid], 3),
            "p_value": round(p_by_id[lid], 4),
            "q_value": round(q_by_id[lid], 4),
            "significant": bool(sig_by_id[lid]),
            "first_year": r["y0"], "last_year": r["y1"],
            "first_pm": _endpoint_pm(conn, corpus, lid, r["y0"]),
            "last_pm": _endpoint_pm(conn, corpus, lid, r["y1"]),
        }

    rising = [pack(r) for r in sorted(
        cands, key=lambda r: sen_by_id[r["lemma_id"]], reverse=True)[:limit]]
    falling = [pack(r) for r in sorted(
        cands, key=lambda r: sen_by_id[r["lemma_id"]])[:limit]]
    result = {"corpus": corpus, "rising": rising, "falling": falling}
    _cache_put(conn, cache_key, result)
    conn.close()
    return result


@app.get("/api/explore/compare")
def explore_compare(limit: int = 160, min_count: int = 80, max_dp: float = 0.80):
    """Cross-corpus view — the only place the two axes meet, explicitly as a
    comparison. Two parts:
      · pairs   — words with drift in BOTH corpora → agreement/divergence scatter.
      · keyness — register-distinctive vocabulary by Hardie Log Ratio (effect size,
                  with 95% CI) and Dunning G² (significance, gated at p<0.001), plus
                  Gries' Deviation of Proportions so a one-year spike can't masquerade
                  as a distinctive word.

    The scatter is RANK-based, not raw-magnitude. Cosine drift magnitude is not
    commensurable across corpora — it depends on slice count (31 vs 11), span,
    corpus size and register — so plotting raw parliament drift against raw news
    drift would imply a false 'equal amount of change' diagonal. Instead each word
    gets its percentile rank within its OWN corpus's content-word drift
    distribution; the diagonal then means 'a comparably high (or low) mover in each
    corpus', which is a defensible notion of agreement. Raw scores travel along for
    the tooltip.

    Fully deterministic → served from `explore_cache` when warm (≈35 s recompute
    only on the first call after a re-ingest changes the data signature)."""
    conn = db()
    cache_key = f"compare:v2:{limit}:{min_count}:dp{max_dp}"  # v2: G²/Hardie LR keyness (#46)
    cached = _cache_get(conn, cache_key)
    if cached is not None:
        conn.close()
        return cached

    def _corpus_drift_ranks(corpus: str) -> dict:
        """normalized_lemma → {lemma, lemma_id, drift, rank} where rank is the
        percentile (0..1) of this word's drift within all content words of the
        corpus (deduped by surface, max drift wins)."""
        rows = conn.execute(
            """
            SELECT l.lemma, l.normalized_lemma, d.lemma_id, MAX(d.drift_score) AS drift
            FROM diachronic_drift d JOIN lemmas l ON l.id = d.lemma_id
            WHERE d.corpus = ? AND l.pos IN ('noun', 'adj', 'verb')
              AND LENGTH(l.normalized_lemma) >= 4
            GROUP BY l.normalized_lemma
            """,
            (corpus,),
        ).fetchall()
        kept = [r for r in rows if _keep_mover(r["lemma"], r["normalized_lemma"])]
        kept.sort(key=lambda r: r["drift"])
        denom = max(len(kept) - 1, 1)
        out = {}
        for i, r in enumerate(kept):
            out[r["normalized_lemma"]] = {
                "lemma": r["lemma"], "lemma_id": r["lemma_id"],
                "drift": round(r["drift"], 4), "rank": round(i / denom, 4),
            }
        return out

    parl_ranks = _corpus_drift_ranks("parliament")
    news_ranks = _corpus_drift_ranks("news")
    common = [nl for nl in parl_ranks if nl in news_ranks]
    # Most-prominent first: highest combined rank (top-movers in both corpora).
    common.sort(key=lambda nl: parl_ranks[nl]["rank"] + news_ranks[nl]["rank"], reverse=True)
    pairs = []
    for nl in common[:limit]:
        p, n = parl_ranks[nl], news_ranks[nl]
        pairs.append({
            "lemma": p["lemma"], "lemma_id": p["lemma_id"],
            "parliament": p["rank"], "news": n["rank"],
            "parliament_drift": p["drift"], "news_drift": n["drift"],
        })

    # --- keyness: distinctive vocabulary by per-million log-ratio, DP-gated ---
    # Keyness on summed counts alone can crown a word that spikes in a single
    # debate / news burst. We replace the crude presence-fraction guard with
    # Gries' Deviation of Proportions (DP). Size each corpus's "parts" by yearly
    # volume → expected share sᵢ for year i. For a word with per-year counts cᵢ
    # (total C), its observed share is vᵢ = cᵢ/C, and
    #     DP = ½ · Σᵢ |vᵢ − sᵢ|        (sum over ALL corpus years, absent ⇒ vᵢ=0)
    # DP=0 ⇒ perfectly even (tracks corpus volume); DP→1 ⇒ all mass in one year.
    # A word may only be called distinctive-to-a-corpus when it is well dispersed
    # (DP ≤ max_dp) in THAT corpus — so a one-off spike is excluded as the very
    # thing dispersion is meant to catch, while still allowing it in the other
    # corpus's ranking if it is steady there.
    totals = {r["corpus"]: r["t"] for r in conn.execute(
        "SELECT corpus, SUM(count) AS t FROM frequency_timeseries GROUP BY corpus")}
    tp, tn = totals.get("parliament", 0) or 1, totals.get("news", 0) or 1
    # Expected part sizes sᵢ: year volume / corpus total, per corpus.
    year_vol: dict[str, dict[int, int]] = {}
    for r in conn.execute(
        "SELECT corpus, year, SUM(count) AS c FROM frequency_timeseries GROUP BY corpus, year"):
        year_vol.setdefault(r["corpus"], {})[r["year"]] = r["c"]
    parts = {c: {y: v / (totals.get(c, 0) or 1) for y, v in yv.items()}
             for c, yv in year_vol.items()}

    krows = conn.execute(
        """
        WITH pl AS (SELECT lemma_id, SUM(count) c FROM frequency_timeseries
                      WHERE corpus='parliament' GROUP BY lemma_id),
             nw AS (SELECT lemma_id, SUM(count) c FROM frequency_timeseries
                      WHERE corpus='news' GROUP BY lemma_id)
        SELECT pl.lemma_id AS lemma_id, l.lemma, l.normalized_lemma, pl.c AS pc, nw.c AS nc
        FROM pl JOIN nw ON nw.lemma_id = pl.lemma_id
        JOIN lemmas l ON l.id = pl.lemma_id
        WHERE l.pos IN ('noun', 'adj', 'verb') AND LENGTH(l.normalized_lemma) >= 4
          AND (pl.c + nw.c) >= ?
        """,
        (min_count,),
    ).fetchall()

    # Per-year counts for candidate lemmas (chunked to stay under SQLite's
    # bound-variable limit), so DP can be computed without scanning the table once
    # per word.
    cand_ids = [r["lemma_id"] for r in krows]
    ts: dict[tuple[int, str], dict[int, int]] = {}
    for off in range(0, len(cand_ids), 800):
        chunk = cand_ids[off:off + 800]
        qmarks = ",".join("?" * len(chunk))
        for r in conn.execute(
            f"SELECT lemma_id, corpus, year, count FROM frequency_timeseries "
            f"WHERE lemma_id IN ({qmarks})", chunk):
            ts.setdefault((r["lemma_id"], r["corpus"]), {})[r["year"]] = r["count"]

    def _dp(lemma_id: int, corpus: str) -> float:
        counts = ts.get((lemma_id, corpus))
        s = parts.get(corpus, {})
        if not counts or not s:
            return 1.0
        total = sum(counts.values())
        if total <= 0:
            return 1.0
        dev = sum(abs(counts.get(y, 0) / total - sy) for y, sy in s.items())
        return 0.5 * dev

    parl_scored, news_scored = [], []
    kseen: set = set()
    for r in krows:
        if not _keep_mover(r["lemma"], r["normalized_lemma"]) or r["normalized_lemma"] in kseen:
            continue
        kseen.add(r["normalized_lemma"])
        pc, nc = r["pc"], r["nc"]
        pm_p = pc / tp * 1e6
        pm_n = nc / tn * 1e6
        # Effect size + significance separated (#46): Hardie Log Ratio (with CI) is the
        # effect size; Dunning G² is the significance. A word is distinctive only when
        # the evidence is significant (G² ≥ 10.83 ↔ p<0.001), it leans to that corpus
        # (sign of LR) and it's well-dispersed there (DP ≤ max_dp) — no arbitrary smoother.
        ratio, ci_lo, ci_hi = _hardie_log_ratio(pc, nc, tp, tn)
        g2 = _log_likelihood_g2(pc, nc, tp, tn)
        dp_p = _dp(r["lemma_id"], "parliament")
        dp_n = _dp(r["lemma_id"], "news")
        entry = {"lemma": r["lemma"], "lemma_id": r["lemma_id"],
                 "log_ratio": round(ratio, 3),
                 "log_ratio_ci_lo": round(ci_lo, 3), "log_ratio_ci_hi": round(ci_hi, 3),
                 "g2": round(g2, 1),
                 "pm_parliament": round(pm_p, 2), "pm_news": round(pm_n, 2),
                 "dp_parliament": round(dp_p, 3), "dp_news": round(dp_n, 3)}
        if g2 < 10.83:  # not significant at p<0.001 → not distinctive of either corpus
            continue
        if ratio > 0 and dp_p <= max_dp:
            parl_scored.append(entry)
        elif ratio < 0 and dp_n <= max_dp:
            news_scored.append(entry)
    parl_scored.sort(key=lambda x: x["log_ratio"], reverse=True)
    news_scored.sort(key=lambda x: x["log_ratio"])
    parliament_distinctive = parl_scored[:30]
    news_distinctive = news_scored[:30]
    result = {
        "pairs": pairs,
        "keyness": {"parliament": parliament_distinctive, "news": news_distinctive},
    }
    _cache_put(conn, cache_key, result)
    conn.close()
    return result


@app.get("/api/health")
def health():
    return {"ok": True, "db": DB_PATH, "db_exists": os.path.exists(DB_PATH)}
