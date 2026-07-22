"""The paradigm engine must refuse rather than guess (audit F40, F42).

Both bugs share one shape: a missing signal silently became a default.

  F40  greek_accent's accent table was lowercase-monotonic only, so capitals (Ίκαρος)
       and polytonic vowels read as "unaccented" (-1). The caller clamped -1 to 0 and
       wrote a fresh accent onto syllable 1 — while the original survived. 171 shipped
       forms carried two accents (ἔναύλος, μούστακᾶτος): impossible in any orthography
       of Greek, and all of them indexed as resolvable inflected forms.

  F42  `g in ("masculine", "")` let an unknown gender take the masculine -ος paradigm.
       καταστρώματος (itself the genitive of κατάστρωμα, wrongly stored as a lemma)
       generated καταστρώματε, καταστρώματοι.
"""

import os
import sys
import unicodedata

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
from ingest.greek_accent import (  # noqa: E402
    has_stress_mark, is_polytonic, stress_index_from_start,
)
from ingest.paradigm_engine import generate  # noqa: E402


def n_accents(word: str) -> int:
    d = unicodedata.normalize("NFD", word)
    return sum(1 for ch in d if ch in {"́", "͂", "̀"})


# ----------------------------------------------------------------- F40: detection
@pytest.mark.parametrize("word", ["άνθρωπος", "λόγος", "χώρα", "καλός"])
def test_monotonic_lowercase_stress_is_seen(word):
    assert has_stress_mark(word)
    assert stress_index_from_start(word) >= 0


@pytest.mark.parametrize("word", ["Ίκαρος", "Άννα", "Έλλη", "Όλγα", "Ύδρα", "Ώρα"])
def test_capital_accents_are_seen(word):
    """Ίκαρος was one of 36 lemmas returning -1 despite being polysyllabic."""
    assert has_stress_mark(word), word
    assert stress_index_from_start(word) == 0, word


@pytest.mark.parametrize("word", ["ἔναυλος", "μουστακᾶτος", "ἄνθρωπος", "λόγῳ"])
def test_polytonic_accents_are_seen(word):
    assert has_stress_mark(word), word


def test_unaccented_polysyllable_reports_minus_one():
    assert stress_index_from_start("ανθρωπος") == -1


@pytest.mark.parametrize("word", ["ἔναυλος", "ἄνθρωπος", "μουστακᾶτος", "λόγῳ"])
def test_polytonic_is_detected(word):
    assert is_polytonic(word), word


@pytest.mark.parametrize("word", ["άνθρωπος", "λόγος", "Ίκαρος", "χώρα"])
def test_monotonic_is_not_flagged_polytonic(word):
    assert not is_polytonic(word), word


# ----------------------------------------------------------------- F40: refusal
@pytest.mark.parametrize("lemma", ["ἔναυλος", "μουστακᾶτος", "ἄνθρωπος"])
def test_polytonic_lemmas_generate_nothing(lemma):
    assert generate(lemma, "noun", "masculine") == []
    assert generate(lemma, "adj", None) == []


def test_unaccented_polysyllable_generates_nothing():
    """The -1 case must be a refusal, not 'accent syllable 1'."""
    assert generate("ανθρωπος", "noun", "masculine") == []


def test_no_generated_form_ever_carries_two_accents():
    """The invariant the 171 shipped forms violated."""
    for lemma, pos, gender in [
        ("άνθρωπος", "noun", "masculine"), ("λόγος", "noun", "masculine"),
        ("κύμα", "noun", "neuter"), ("χώρα", "noun", "feminine"),
        ("καλός", "adj", None), ("Ίκαρος", "noun", "masculine"),
    ]:
        for form, _tags in generate(lemma, pos, gender):
            assert n_accents(form) <= 1, f"{lemma} -> {form} has {n_accents(form)} accents"


def test_a_monosyllable_is_still_allowed():
    """The -1 refusal must not kill legitimately unaccented monosyllables."""
    assert stress_index_from_start("φως") == -1
    # single syllable → the guard does not fire; class support is a separate question
    generate("φως", "noun", "neuter")  # must not raise


# ----------------------------------------------------------------- F42: gender
@pytest.mark.parametrize("lemma", ["καταστρώματος", "θελήματος"])
def test_gender_null_noun_generates_nothing(lemma):
    """These produced καταστρώματε / θελήματοι in the shipped DB."""
    assert generate(lemma, "noun", None) == []
    assert generate(lemma, "noun", "") == []


def test_gender_null_is_refused_for_every_nominal_class():
    for lemma in ["λόγος", "κύμα", "δώρο", "παιδί", "χώρα", "νίκη"]:
        assert generate(lemma, "noun", None) == [], lemma


def test_known_gender_still_generates():
    """The refusal must not break the classes that do have gender."""
    assert generate("λόγος", "noun", "masculine")
    assert generate("κύμα", "noun", "neuter")
    assert generate("χώρα", "noun", "feminine")


def test_wrong_gender_for_the_ending_is_refused():
    """A neuter -ος (κράτος) must not receive the masculine paradigm."""
    assert generate("κράτος", "noun", "neuter") == []


def test_feminine_in_ma_does_not_take_the_neuter_oblique_stem():
    """κρέμα/φόρμα with a stated feminine gender must not get -ματ-."""
    for form, _ in generate("κρέμα", "noun", "feminine"):
        assert "ματ" not in form, form
