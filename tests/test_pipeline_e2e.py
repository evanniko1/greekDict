"""End-to-end: ingest the synthetic fixture, build the index, and assert that
the core product promise works — an inflected form resolves to its lemma with
features. Runs WITHOUT any download. Run: pytest tests/ -q
"""

import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "pipelines", "ingest"))

import ingest_kaikki  # noqa: E402
import build_search_index  # noqa: E402
from normalize_greek import normalize  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "mini_el.jsonl")


def _build_db():
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "test.sqlite")
    ingest_kaikki.ingest(FIXTURE, "el-wiktionary", db, limit=None)
    build_search_index.build(db)
    return db


def test_ingest_counts():
    db = _build_db()
    conn = sqlite3.connect(db)
    # 3 Greek lemmas; the en "skip-me" entry AND the "ανθρώπων" form-of stub
    # must both be dropped (the stub is recoverable from άνθρωπος's inflections).
    assert conn.execute("SELECT count(*) FROM lemmas").fetchone()[0] == 3
    # table-tags pseudo-form must be filtered out.
    forms = conn.execute("SELECT form FROM forms").fetchall()
    assert ("masculine",) not in forms
    conn.close()


def test_form_of_stub_not_a_competing_lemma():
    """The standalone "ανθρώπων = genitive plural of άνθρωπος" page must NOT
    become its own lemma, and the form must resolve to άνθρωπος ranked first."""
    db = _build_db()
    conn = sqlite3.connect(db)
    # No standalone lemma row for the form-of surface.
    assert conn.execute(
        "SELECT count(*) FROM lemmas WHERE normalized_lemma = ?", (normalize("ανθρώπων"),)
    ).fetchone()[0] == 0
    # Mirror the API ranking query: top result must be the form → άνθρωπος.
    rows = conn.execute(
        """SELECT l.lemma, si.surface_type, si.rank_weight
           FROM search_index si JOIN lemmas l ON l.id = si.lemma_id
           WHERE si.normalized_surface = ?
           ORDER BY si.rank_weight DESC""",
        (normalize("ανθρώπων"),),
    ).fetchall()
    assert rows, "ανθρώπων must still resolve"
    assert rows[0][0] == "άνθρωπος"
    assert rows[0][1] == "form"
    conn.close()


def test_inflected_form_resolves_to_lemma():
    db = _build_db()
    conn = sqlite3.connect(db)
    key = normalize("ανθρώπων")  # genitive plural, accented
    row = conn.execute(
        """SELECT l.lemma, si.surface_type, si.features
           FROM search_index si JOIN lemmas l ON l.id = si.lemma_id
           WHERE si.normalized_surface = ?""",
        (key,),
    ).fetchone()
    assert row is not None
    assert row[0] == "άνθρωπος"
    assert row[1] == "form"
    assert "genitive" in row[2] and "plural" in row[2]
    conn.close()


def test_unaccented_query_resolves():
    db = _build_db()
    conn = sqlite3.connect(db)
    # user types without accents
    key = normalize("ανθρωπων")
    row = conn.execute(
        "SELECT lemma_id FROM search_index WHERE normalized_surface = ?", (key,)
    ).fetchone()
    assert row is not None
    conn.close()


def test_relations_extracted_and_resolved():
    """Wiktionary relation lists (entry + sense level) land in `relations`, and
    targets that exist as lemmas get their target_lemma_id linked."""
    db = _build_db()
    conn = sqlite3.connect(db)
    logos = conn.execute(
        "SELECT id FROM lemmas WHERE normalized_lemma = ?", (normalize("λόγος"),)
    ).fetchone()[0]
    rels = conn.execute(
        "SELECT relation_type, target_text, target_lemma_id, source FROM relations WHERE source_lemma_id = ?",
        (logos,),
    ).fetchall()
    by_target = {r[1]: r for r in rels}
    # entry-level synonym, entry-level related, and sense-level synonym all captured.
    assert by_target["ομιλία"][0] == "synonym"
    assert by_target["λαλιά"][0] == "synonym"
    assert by_target["άνθρωπος"][0] == "related"
    # every relation keeps its source.
    assert all(r[3] == "el-wiktionary" for r in rels)
    # άνθρωπος is in the store -> target_lemma_id resolved; ομιλία is not -> NULL.
    anthropos = conn.execute(
        "SELECT id FROM lemmas WHERE normalized_lemma = ?", (normalize("άνθρωπος"),)
    ).fetchone()[0]
    assert by_target["άνθρωπος"][2] == anthropos
    assert by_target["ομιλία"][2] is None
    conn.close()


def test_junk_relation_targets_filtered():
    """Descriptive Wiktionary cruft (category prose with non-breaking spaces or
    the 'Βικιλεξικό' self-reference) must not leak into the graph as fake nodes."""
    entry = {
        "synonyms": [
            {"word": "ομιλία"},  # real neighbour, kept
            {"word": "-γενής Νεοελληνικές λέξεις\xa0στο Βικιλεξικό"},  # junk
            {"word": "λέξεις με επίθημα\nκάτι"},  # newline junk
        ],
    }
    rels = ingest_kaikki.extract_relations(entry)
    targets = {t for _, t in rels}
    assert "ομιλία" in targets
    assert all("Βικιλεξικ" not in t and "\xa0" not in t and "\n" not in t for t in targets)
    assert len(targets) == 1


def test_source_attribution_recorded():
    """CC BY-SA / GFDL compliance gate: ingesting a source must record its
    attribution row (license, source URL, modification notice, retrieved date)."""
    db = _build_db()
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT source_url, license, attribution_text, retrieved_at "
        "FROM source_attributions WHERE source_name = ?",
        ("el-wiktionary",),
    ).fetchone()
    assert row is not None, "el-wiktionary attribution must be recorded at ingest"
    source_url, license_, text, retrieved = row
    assert source_url and "wiktionary.org" in source_url
    assert license_ and "CC BY-SA" in license_
    assert text and "Βικιλεξικό" in text and "τροποποιη" in text  # modification noted
    assert retrieved  # non-empty ISO date
    conn.close()


def test_verb_form_resolves():
    db = _build_db()
    conn = sqlite3.connect(db)
    key = normalize("έγραψες")
    row = conn.execute(
        """SELECT l.lemma FROM search_index si JOIN lemmas l ON l.id = si.lemma_id
           WHERE si.normalized_surface = ? AND si.surface_type='form'""",
        (key,),
    ).fetchone()
    assert row is not None and row[0] == "γράφω"
    conn.close()


if __name__ == "__main__":
    import traceback
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(funcs) - failed}/{len(funcs)} passed")
    sys.exit(1 if failed else 0)
