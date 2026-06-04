"""Tests for supervised domain attribution (#38). Run: pytest tests/ -q

Covers the pure, gensim/sklearn-free parts of `classify_domains.py`:

`SliceReader` — the pooled token stream over diachronic slices. Slices are already
normalize()-d and space-separated, so tokenization is a bare split; it must skip
blank lines and be RE-iterable (gensim reads it once for vocab, once per epoch).

`_gold_domains(conn)` — lemma_id → set of Wiktionary field tags (senses.tags ∩
FIELD_DOMAINS). Single-tag lemmas are clean training labels; multi-tag lemmas are
kept (the caller excludes them from training but writes them as gold); non-field
tags and malformed JSON are ignored.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest"))

from classify_domains import SliceReader, _gold_domains, FIELD_DOMAINS  # noqa: E402


def test_slicereader_tokenizes_and_skips_blank(tmp_path):
    a = tmp_path / "1989.txt"
    a.write_text("κυριες και κυριοι\n\n  \nσυναδελφοι\n", encoding="utf-8")
    sents = list(SliceReader([str(a)]))
    assert sents == [["κυριες", "και", "κυριοι"], ["συναδελφοι"]]


def test_slicereader_is_reiterable_and_pools_files(tmp_path):
    a = tmp_path / "a.txt"; a.write_text("alpha beta\n", encoding="utf-8")
    b = tmp_path / "b.txt"; b.write_text("gamma\n", encoding="utf-8")
    r = SliceReader([str(a), str(b)])
    first = list(r)
    second = list(r)  # must reopen on every __iter__, not exhaust
    assert first == second == [["alpha", "beta"], ["gamma"]]


def _mk_conn(rows):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE senses (lemma_id INTEGER, tags TEXT)")
    conn.executemany("INSERT INTO senses (lemma_id, tags) VALUES (?,?)", rows)
    return conn


def test_gold_single_and_multi_tag():
    conn = _mk_conn([
        (1, '["medicine"]'),
        (2, '["law", "politics"]'),
    ])
    gold = _gold_domains(conn)
    assert gold[1] == {"medicine"}
    assert gold[2] == {"law", "politics"}


def test_gold_ignores_non_field_tags():
    # 'feminine'/'plural' are grammatical tags, not subject fields → dropped.
    conn = _mk_conn([(1, '["feminine", "medicine", "plural"]')])
    gold = _gold_domains(conn)
    assert gold[1] == {"medicine"}


def test_gold_skips_malformed_and_empty():
    conn = _mk_conn([
        (1, "not json"),
        (2, '["sports"]'),
        (3, '[]'),
    ])
    gold = _gold_domains(conn)
    assert 1 not in gold and 3 not in gold
    assert gold[2] == {"sports"}


def test_field_domains_match_api_list():
    # 18 broad fields — guards against drift between pipeline and API constant.
    assert len(FIELD_DOMAINS) == 18
    assert "medicine" in FIELD_DOMAINS and "nautical" in FIELD_DOMAINS
