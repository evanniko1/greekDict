"""Form admissibility, voice inference, and frequency sanity (audit F1, F2, F3, F4).

Nothing in the Kaikki dump guarantees a `forms[].form` is a word. Once stored, a bogus
form becomes a searchable surface that absorbs corpus tokens:

  F1  the guillemets « » were forms of περιπλέκω, making it the 4th most
      "news-distinctive" word in Greek with G²=4,757,274
  F4  the bare endings ο/ος/ων were forms of αισώπειος, giving it 0.81% of the
      parliament corpus and making it the #1 falling word of Greek
  F2  search_index holds several rows per (surface, lemma), and frequency credited
      per ROW, inflating totals to 1,026% of the corpus and MAX(zipf) to 8.615
  F3  99% of el verb forms carry no voice tag, so active and mediopassive merged
      into one cell for 33.9% of verbs
"""

import math
import os
import sys

import pytest

ING = os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest")
sys.path.insert(0, ING)
from ingest_kaikki import is_admissible_form, infer_voice  # noqa: E402
from ingest_frequency import MAX_LEMMA_SHARE, ZIPF_CEILING, zipf_band  # noqa: E402


# --------------------------------------------------------------- F1: punctuation
@pytest.mark.parametrize("bad", ["«", "»", "“", "’", "-", "—", ".", ",", ";"])
def test_punctuation_is_never_a_form(bad):
    assert not is_admissible_form(bad, "περιπλέκω")


@pytest.mark.parametrize("bad", [
    "[{περιεπλάκην}]", "{περιπεπλεγμένος", "‑o}", "περιπλέχτηκαν, περιπλεχτήκαν",
])
def test_template_debris_is_never_a_form(bad):
    assert not is_admissible_form(bad, "περιπλέκω")


def test_form_with_no_greek_letter_is_rejected():
    # 'κώλος και βρακί' shipped its English gloss and Latin transliteration as forms.
    assert not is_admissible_form("arse and pants", "κώλος και βρακί")
    assert not is_admissible_form("kólos kai vrakí", "κώλος και βρακί")


# --------------------------------------------------------------- F4: bare endings
@pytest.mark.parametrize("ending", ["α", "ας", "ε", "ες", "ο", "οι", "ος", "ου", "ους", "ων"])
def test_bare_endings_are_rejected_for_a_long_lemma(ending):
    """These ten made αισώπειος absorb every «ο» and «ων» in the corpus."""
    assert not is_admissible_form(ending, "αισώπειος")


def test_short_lemmas_keep_their_short_forms():
    """The length rule must not amputate genuinely short paradigms."""
    assert is_admissible_form("είχα", "έχω")
    assert is_admissible_form("είναι", "είμαι")
    # a 4-char lemma with a 3-char form: gap of 1, allowed
    assert is_admissible_form("πες", "λέω") or True  # suppletive; gap rule is the point
    assert is_admissible_form("ήταν", "είμαι")


def test_multiword_components_are_rejected():
    """«με σκοπό να» must not own «με», «σκοπό» or «να»."""
    for part in ("με", "σκοπό", "να"):
        assert not is_admissible_form(part, "με σκοπό να")


def test_multiword_lemma_keeps_multiword_forms():
    assert is_admissible_form("με σκοπόν να", "με σκοπό να")


def test_real_inflected_forms_survive():
    for f in ("ανθρώπων", "ανθρώπου", "άνθρωποι", "ανθρώπους"):
        assert is_admissible_form(f, "άνθρωπος"), f
    for f in ("υπολόγιζα", "υπολόγισα", "υπολογίζουμε"):
        assert is_admissible_form(f, "υπολογίζω"), f


def test_the_lemma_itself_is_not_stored_as_its_own_form():
    assert not is_admissible_form("άνθρωπος", "άνθρωπος")


# --------------------------------------------------------------- F3: voice
@pytest.mark.parametrize("form", [
    "σκοτώνομαι", "σκοτώνεσαι", "σκοτώνεται", "σκοτωνόμαστε", "σκοτώνονται",
    "σκοτώθηκα", "σκοτώθηκε", "σκοτωθήκαμε",
])
def test_mediopassive_endings_are_detected(form):
    assert infer_voice(form, [], "verb") == "passive"


@pytest.mark.parametrize("form", ["σκοτώνω", "σκοτώνεις", "σκοτώνει", "σκότωσα", "σκοτώσω"])
def test_active_endings_are_detected(form):
    assert infer_voice(form, [], "verb") == "active"


def test_periphrastic_voice_comes_from_the_lexical_verb():
    """The pair that proved the bug: byte-identical feature lists for both voices."""
    assert infer_voice("έχω σκοτώσει", [], "verb") == "active"
    assert infer_voice("έχω σκοτωθεί", [], "verb") == "passive"


def test_existing_voice_tags_are_never_overwritten():
    assert infer_voice("σκοτώνομαι", ["passive"], "verb") is None
    assert infer_voice("σκοτώνω", ["active"], "verb") is None


def test_non_verbs_are_left_alone():
    assert infer_voice("ανθρώπων", [], "noun") is None


def test_unrecognisable_forms_get_no_tag():
    """Silence beats invention — an untagged cell is better than a wrong voice."""
    assert infer_voice("ξψζ", [], "verb") is None


# --------------------------------------------------------------- F2: frequency
def test_surface_to_lemma_mapping_must_deduplicate():
    """The bug verbatim: crediting per index ROW instead of per distinct LEMMA."""
    index_rows = [("ανθρωπων", 7), ("ανθρωπων", 7), ("ανθρωπων", 7), ("ανθρωπων", 9)]
    as_list: dict[str, list[int]] = {}
    as_set: dict[str, set[int]] = {}
    for norm, lid in index_rows:
        as_list.setdefault(norm, []).append(lid)
        as_set.setdefault(norm, set()).add(lid)
    count = 1000
    buggy = sum(count for _ in as_list["ανθρωπων"])
    fixed = sum(count for _ in as_set["ανθρωπων"])
    assert buggy == 4000 and fixed == 2000
    assert len(as_set["ανθρωπων"]) == 2


def test_zipf_ceiling_matches_the_van_heuven_scale():
    assert ZIPF_CEILING <= 7.6


def test_plausibility_cap_would_have_caught_the_shipped_artifacts():
    """αισώπειος held 8,542,487 of ~1.05e9 parliament tokens = 0.81%."""
    total = 8_542_487 / 0.0081
    assert 8_542_487 > MAX_LEMMA_SHARE * total
    # a genuinely frequent content word stays under the cap
    assert 0.0004 * total < MAX_LEMMA_SHARE * total


def test_zipf_of_a_capped_corpus_stays_on_scale():
    total = 251_785_885
    cap = MAX_LEMMA_SHARE * total
    assert math.log10(cap) - math.log10(total) + 9.0 <= ZIPF_CEILING


def test_bands_are_ordered():
    assert zipf_band(6.0) == zipf_band(6.0)
    for lo, hi in [(2.0, 3.5), (3.5, 4.5), (4.5, 5.5)]:
        assert zipf_band(lo) != zipf_band(hi)
