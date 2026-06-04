"""Tests for cross-language (en→el) gloss extraction (#39). Run: pytest tests/ -q

`_phrases(gloss)` turns one English gloss into the clean leading headword phrase(s)
that become en→el lookup keys. It is tuned for PRECISION (a wrong key sends a
searcher to the wrong Greek word): it drops parentheticals, keeps only short ASCII
phrases, strips leading articles, and skips cross-reference / form-of glosses.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest"))

from build_gloss_index import _phrases  # noqa: E402


def test_simple_single_word():
    assert _phrases("wolf") == ["wolf"]


def test_drops_parenthetical_clarification():
    # "bone (part of skeleton)" → just "bone"
    assert _phrases("bone (part of skeleton)") == ["bone"]


def test_splits_on_semicolon_and_comma_in_order():
    # Order matters: the first clause is the primary translation (higher weight).
    assert _phrases("eagle; kite (toy)") == ["eagle", "kite"]
    assert _phrases("sunlight, daylight") == ["sunlight", "daylight"]


def test_strips_leading_article():
    assert _phrases("a clever person") == ["clever person"]
    assert _phrases("to book a seat") == ["book a seat"]


def test_skips_cross_reference_glosses():
    assert _phrases("for the constellation see Αετός (Aetós)") == []
    assert _phrases("alternative form of φοβάμαι") == []
    assert _phrases("plural of βιβλίο") == []


def test_rejects_long_phrases_and_non_ascii():
    # >3 words → not a headword; Greek text must never leak into the key.
    assert _phrases("a violent person with wild and unpredictable behaviour") == []
    assert _phrases("νερό") == []


def test_drops_bare_function_words():
    assert _phrases("of; the") == []


def test_multiword_translation_kept():
    assert _phrases("eagle ray") == ["eagle ray"]
