"""Tests for multi-hop el prose etymology parsing (#34). Run: pytest tests/ -q

The parser walks the whole " < " chain and emits one typed etymon per step that
names a recognised source language, in `seq` order (immediate ancestor first).
Steps with no recognised language (pure internal Greek morphology, redirects,
"missing etymology") are intentionally skipped — we never assert an ancestor we
can't type. Connector words ("ρίζα", "λέξη") between a language and its term are
skipped so we capture the real ancestor.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest"))

from ingest_kaikki import parse_el_etymology_prose  # noqa: E402


def test_multihop_chain_order_and_relations():
    text = "Ιανουάριος < ελληνιστική κοινή Ἰανουάριος < λατινική ianuarius < πρωτοϊνδοευρωπαϊκή *yeh₂-"
    out = parse_el_etymology_prose(text)
    assert [(rel, lang, term, seq) for (rel, lang, term, seq) in out] == [
        ("inherited", "grc-koi", "Ἰανουάριος", 0),
        ("borrowed", "la", "ianuarius", 1),
        ("inherited", "ine-pro", "*yeh₂-", 2),
    ]


def test_all_greek_stages_inherited():
    text = "υγειά < (κληρονομημένο) μεσαιωνική ελληνική ὑγειά < ελληνιστική κοινή ὑγεία < αρχαία ελληνική ὑγίεια"
    out = parse_el_etymology_prose(text)
    assert [(o[1], o[2]) for o in out] == [("gkm", "ὑγειά"), ("grc-koi", "ὑγεία"), ("grc", "ὑγίεια")]
    assert all(o[0] == "inherited" for o in out)


def test_connector_word_skipped():
    # "πρωτοϊνδοευρωπαϊκή ρίζα *reh-" — the connector "ρίζα" must not become the term
    text = "ρεαλισμός < (λόγιο δάνειο) γαλλική réal < λατινική realis < πρωτοϊνδοευρωπαϊκή ρίζα *reh-"
    out = parse_el_etymology_prose(text)
    assert ("borrowed", "fr", "réal", 0) == out[0]
    assert out[-1][1] == "ine-pro" and out[-1][2] == "*reh-"


def test_internal_and_redirect_yield_nothing():
    # pure affix derivation — no recognised source language
    assert parse_el_etymology_prose("λαδί < λάδ(ι) + -ί") == []
    # redirect / missing etymology
    assert parse_el_etymology_prose("Ιάνος < → λείπει η ετυμολογία") == []
    assert parse_el_etymology_prose("Σαββάτο < → δείτε τη λέξη Σάββατο") == []


def test_dedup_repeated_ancestor():
    # the same (relation, lang, term) must not be emitted twice
    text = "x < αρχαία ελληνική λόγος < αρχαία ελληνική λόγος"
    out = parse_el_etymology_prose(text)
    assert len(out) == 1
