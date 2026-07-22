"""Accent-distinguished homographs must survive ingest (R2 / audit F21).

Accent is phonemic in Modern Greek. The lemma identity key used to be
(normalized_lemma, pos), which folds accents, so the second homograph of a pair to
arrive was silently dropped — the shipped DB had 0 rows for ποτέ "never",
νομός "prefecture", δουλεία "slavery" and χαλί "carpet".

The audit noted that no test would have caught this. This is that test.
"""

import os
import sqlite3
import sys

import pytest

ING = os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest")
sys.path.insert(0, ING)
from ingest_kaikki import upsert_lemma, find_lemma_id  # noqa: E402
from normalize_greek import normalize  # noqa: E402

# (word_a, word_b, pos) — real Greek pairs that differ ONLY by accent and share a POS,
# so the folded key collapses them.
HOMOGRAPHS = [
    ("νόμος", "νομός", "noun"),      # law / prefecture
    ("ποτέ", "πότε", "adv"),         # never / when
    ("δουλειά", "δουλεία", "noun"),  # job / slavery
    ("χάλι", "χαλί", "noun"),        # mess / carpet
    ("γέρος", "γερός", "adj"),       # old man / sturdy
]


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    with open(os.path.join(ING, "schema.sql"), encoding="utf-8") as fh:
        c.executescript(fh.read())
    yield c
    c.close()


@pytest.mark.parametrize("a,b,pos", HOMOGRAPHS)
def test_homograph_pair_yields_two_distinct_lemmas(conn, a, b, pos):
    ida = upsert_lemma(conn, a, pos, None, "el-wiktionary")
    idb = upsert_lemma(conn, b, pos, None, "el-wiktionary")
    assert ida != idb, f"{a} and {b} collapsed into one lemma row"

    rows = conn.execute(
        "SELECT lemma FROM lemmas WHERE pos = ? ORDER BY lemma", (pos,)
    ).fetchall()
    assert sorted(r[0] for r in rows) == sorted([a, b])


@pytest.mark.parametrize("a,b,pos", HOMOGRAPHS)
def test_both_members_share_one_search_key(conn, a, b, pos):
    """They stay distinct as lemmas but must still be findable by the folded key —
    that is the whole point of separating identity from the search key."""
    upsert_lemma(conn, a, pos, None, "el-wiktionary")
    upsert_lemma(conn, b, pos, None, "el-wiktionary")
    assert normalize(a) == normalize(b)
    n = conn.execute(
        "SELECT COUNT(*) FROM lemmas WHERE normalized_lemma = ?", (normalize(a),)
    ).fetchone()[0]
    assert n == 2, "both homographs must be reachable from the shared search key"


def test_same_word_from_both_editions_still_merges(conn):
    """The merge that the folded key was there to achieve must still work."""
    a = upsert_lemma(conn, "άνθρωπος", "noun", "masculine", "el-wiktionary")
    b = upsert_lemma(conn, "άνθρωπος", "noun", "masculine", "en-wiktionary")
    assert a == b
    sources = conn.execute("SELECT sources FROM lemmas WHERE id = ?", (a,)).fetchone()[0]
    assert sources == "el-wiktionary,en-wiktionary"


def test_same_spelling_different_pos_stays_distinct(conn):
    """POS is still part of the identity."""
    a = upsert_lemma(conn, "καλά", "adv", None, "el-wiktionary")
    b = upsert_lemma(conn, "καλά", "noun", None, "el-wiktionary")
    assert a != b


def test_find_lemma_id_prefers_the_exact_accented_surface(conn):
    law = upsert_lemma(conn, "νόμος", "noun", None, "el-wiktionary")
    county = upsert_lemma(conn, "νομός", "noun", None, "el-wiktionary")
    assert find_lemma_id(conn, "νόμος", "noun") == law
    assert find_lemma_id(conn, "νομός", "noun") == county


def test_find_lemma_id_refuses_to_guess_between_homographs(conn):
    """An ambiguous folded lookup must return None rather than corrupt a random row.

    This is what protects the --etymology-only / --ipa-only / --descendants-only /
    --sense-tags-only passes from attaching data to the wrong word.
    """
    upsert_lemma(conn, "νόμος", "noun", None, "el-wiktionary")
    upsert_lemma(conn, "νομός", "noun", None, "el-wiktionary")
    # An unaccented query folds onto both; there is no principled winner.
    assert find_lemma_id(conn, "νομος", "noun") is None


def test_find_lemma_id_falls_back_when_unambiguous(conn):
    """A legacy row stored unaccented is still reachable when only one candidate exists."""
    lid = upsert_lemma(conn, "άνθρωπος", "noun", None, "el-wiktionary")
    assert find_lemma_id(conn, "ανθρωπος", "noun") == lid


def test_schema_does_not_fold_accent_into_the_key(conn):
    ddl = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='lemmas'"
    ).fetchone()[0]
    compact = ddl.replace(" ", "").replace("\n", "")
    assert "UNIQUE(lemma,pos)" in compact
    assert "UNIQUE(normalized_lemma,pos)" not in compact
