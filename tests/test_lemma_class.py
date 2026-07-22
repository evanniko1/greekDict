"""Proper-name classification for the Phase 2 name split (audit F37).

Names are 76% of the lexicon; misclassifying a real word AS a name would hide it from
primary search, and misclassifying a name as content re-pollutes the results. The rule
must be conservative in both directions.
"""

import os
import sqlite3
import sys

import pytest

ING = os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest")
sys.path.insert(0, ING)
from classify_lemma_class import classify, ensure_column  # noqa: E402
from ingest_kaikki import upsert_lemma  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "t.sqlite")
    conn = sqlite3.connect(path)
    with open(os.path.join(ING, "schema.sql"), encoding="utf-8") as fh:
        conn.executescript(fh.read())
    conn.commit()
    conn.close()
    return path


def _add(path, lemma, pos, glosses):
    conn = sqlite3.connect(path)
    lid = upsert_lemma(conn, lemma, pos, None, "el-wiktionary")
    for i, g in enumerate(glosses):
        conn.execute(
            "INSERT INTO senses (lemma_id, sense_index, gloss, source) VALUES (?,?,?,?)",
            (lid, i, g, "el-wiktionary"),
        )
    conn.commit()
    conn.close()
    return lid


def _class_of(path, lid):
    conn = sqlite3.connect(path)
    row = conn.execute("SELECT lemma_class FROM lemmas WHERE id = ?", (lid,)).fetchone()
    conn.close()
    return row[0]


def test_ingest_tags_pos_name_at_insert():
    """upsert_lemma sets lemma_class from POS directly."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(open(os.path.join(ING, "schema.sql"), encoding="utf-8").read())
    name_id = upsert_lemma(conn, "Παπαδόπουλος", "name", None, "el-wiktionary")
    word_id = upsert_lemma(conn, "άνθρωπος", "noun", None, "el-wiktionary")
    assert conn.execute("SELECT lemma_class FROM lemmas WHERE id=?", (name_id,)).fetchone()[0] == "name"
    assert conn.execute("SELECT lemma_class FROM lemmas WHERE id=?", (word_id,)).fetchone()[0] == "content"
    conn.close()


def test_pos_name_is_classified_name(db):
    lid = _add(db, "Παπαδόπουλος", "name", ["επώνυμο"])
    classify(db)
    assert _class_of(db, lid) == "name"


def test_content_word_stays_content(db):
    lid = _add(db, "άνθρωπος", "noun", ["αυτός που ανήκει στην ανθρώπινη φυλή"])
    classify(db)
    assert _class_of(db, lid) == "content"


def test_noun_whose_every_sense_is_a_name_gloss_becomes_name(db):
    """A non-name-POS lemma glossed only «επώνυμο» is a name that slipped the POS tag."""
    lid = _add(db, "Κρανίδης", "noun", ["επώνυμο"])
    classify(db)
    assert _class_of(db, lid) == "name"


def test_homograph_with_a_real_sense_stays_content(db):
    """The crucial case: a word that is BOTH a surname AND a common word keeps content
    class (it has a real sense), so it stays in primary search and is disambiguated at
    ranking — the same principle as the homograph fix."""
    lid = _add(db, "Ξένος", "noun", ["επώνυμο", "αυτός που δεν είναι ντόπιος"])
    classify(db)
    assert _class_of(db, lid) == "content"


def test_gloss_that_merely_mentions_a_name_is_not_a_name(db):
    lid = _add(db, "ονομάζω", "verb", ["δίνω όνομα σε κάποιον"])
    classify(db)
    assert _class_of(db, lid) == "content"


def test_classify_is_idempotent(db):
    lid = _add(db, "Παπαδόπουλος", "name", ["επώνυμο"])
    a = classify(db)
    b = classify(db)
    assert a == b
    assert _class_of(db, lid) == "name"


def test_report_counts(db):
    _add(db, "Παπαδόπουλος", "name", ["επώνυμο"])
    _add(db, "Μαρία", "noun", ["γυναικείο όνομα"])   # gloss-only name
    _add(db, "άνθρωπος", "noun", ["ον"])
    rep = classify(db)
    assert rep["name_lemmas"] == 2
    assert rep["content_lemmas"] == 1
    assert rep["by_pos_tag"] == 1
    assert rep["by_gloss_only"] == 1
