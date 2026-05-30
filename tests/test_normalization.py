"""Tests for the cornerstone Greek normalization. Run: pytest tests/ -q"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest"))

from normalize_greek import normalize, fold_final_sigma, strip_accents, greeklish_to_greek  # noqa: E402


def test_accent_folding():
    assert normalize("άνθρωπος") == normalize("ανθρωπος")
    assert normalize("λόγος") == normalize("λογος")


def test_case_folding():
    assert normalize("Λόγος") == normalize("λόγος")
    assert normalize("ΦΩΣ") == normalize("φως")


def test_final_sigma_folding():
    # final vs medial sigma must share a key
    assert normalize("λόγος") == normalize("λόγοσ")
    assert fold_final_sigma("ως") == "ωσ"


def test_inflected_forms_have_distinct_keys_but_consistent_folding():
    # different forms => different keys (resolution happens via the forms table)
    assert normalize("ανθρώπων") != normalize("άνθρωπος")
    # but the same form spelled with/without accent => same key
    assert normalize("ανθρώπων") == normalize("ανθρωπων")


def test_dialytika_folding():
    # προϊόν: dialytika on iota should be stripped for the key
    assert normalize("προϊόν") == normalize("προιον")


def test_polytonic_folding():
    # polytonic spelling folds to the same key as monotonic
    assert normalize("ἄνθρωπος") == normalize("άνθρωπος")


def test_whitespace_and_empty():
    assert normalize("  λόγος  ") == normalize("λόγος")
    assert normalize("") == ""
    assert normalize("  ") == ""


def test_strip_accents_keeps_letters():
    assert strip_accents("άέήίόύώ") == "αεηιουω"


def test_greeklish_exact_when_unambiguous():
    # 'logos' has no ambiguous vowels in our table -> exact lemma key.
    assert normalize(greeklish_to_greek("logos")) == normalize("λόγος")


def test_greeklish_lossy_on_ambiguous_vowels():
    # 'anthropos' cannot encode ω vs ο, 'kalimera' cannot encode η vs ι:
    # the transliterator is a CANDIDATE generator, not an exact resolver.
    # We only assert it yields plausible Greek (digraph + consonant skeleton),
    # leaving vowel disambiguation to the multi-candidate search layer.
    out = greeklish_to_greek("anthropos")
    assert out  # non-empty
    assert all("Ͱ" <= ch <= "Ͽ" for ch in out)  # all Greek block
    assert out.endswith("σ")


def test_greeklish_digraphs():
    assert greeklish_to_greek("thalassa").startswith("θ")
    assert "χ" in greeklish_to_greek("chara")


if __name__ == "__main__":
    import traceback

    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(funcs) - failed}/{len(funcs)} passed")
    sys.exit(1 if failed else 0)
