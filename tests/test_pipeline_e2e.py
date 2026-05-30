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
    # 3 Greek lemmas; the en "skip-me" entry must be dropped.
    assert conn.execute("SELECT count(*) FROM lemmas").fetchone()[0] == 3
    # table-tags pseudo-form must be filtered out.
    forms = conn.execute("SELECT form FROM forms").fetchall()
    assert ("masculine",) not in forms
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
