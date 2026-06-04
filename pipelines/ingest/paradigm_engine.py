"""Generative κλίση — a conservative, accent-aware Modern Greek paradigm engine.

Wiktionary already supplies inflected forms for ~80–95% of our lemmas; this fills
the *gaps* and lets form→lemma search resolve forms the dump never listed. It is
deliberately CAUTIOUS: it generates only for single-word lemmas whose ending
matches a known productive class, refuses indeclinables, and tags every output
`source='generated'`. Generated forms NEVER overwrite a sourced Wiktionary form —
they only fill missing cells.

Correctness is not asserted, it is *measured*: `validate_against_db` runs the
generator over every lemma that already has Wiktionary forms and reports
per-class agreement, so a class is only enabled in the backfill once its
precision is high. Greek morphology is regular in its endings but its accent
moves (άνθρωπος→ανθρώπου, χώρα→χωρών); the accent logic lives in `greek_accent`.

Feature tags use the same lowercase-English vocabulary the ingested forms use
(`nominative`/`genitive`/`accusative`/`vocative` × `singular`/`plural`, plus
`masculine`/`feminine`/`neuter` for adjectives), so generated forms drop straight
into the existing inflection-grid builder.
"""

from __future__ import annotations

from .greek_accent import (
    strip_tonos,
    stress_pos,
    n_syllables,
    stress_index_from_start,
    set_stress,
    set_stress_from_start,
    hiatus_ambiguous,
)

__all__ = ["generate", "supported_classes"]

CASES = ["nominative", "genitive", "accusative", "vocative"]


def _acc(raw: str, mode: str, stem_k: int) -> str:
    """Place the tonos on `raw` (an unaccented stem+ending) per `mode`.

    stem_k = 0-based from-start index of the stem's own accented nucleus.
    Modes:
      stem        keep the stress on that same stem syllable
      stem_cap3   keep it, but never further back than the antepenult (trisyllaby)
      pen_if_ante if keeping would land on the antepenult-or-back, drop to penult
      penult / ultima / antepenult  absolute, counted from the end
    """
    if mode == "ultima":
        return set_stress(raw, 1)
    if mode == "penult":
        return set_stress(raw, 2)
    if mode == "antepenult":
        return set_stress(raw, 3)
    if mode == "stem":
        return set_stress_from_start(raw, stem_k)
    if mode == "stem_cap3":
        n_from_end = n_syllables(raw) - stem_k
        return set_stress(raw, 3) if n_from_end >= 4 else set_stress_from_start(raw, stem_k)
    if mode == "pen_if_ante":
        n_from_end = n_syllables(raw) - stem_k
        return set_stress(raw, 2) if n_from_end >= 3 else set_stress_from_start(raw, stem_k)
    raise ValueError(mode)


def _emit(stem: str, table: dict, stem_k: int, extra: list[str]) -> list[tuple[str, list[str]]]:
    """table maps (case, number) → (ending, stress_mode). `extra` = extra tags
    (e.g. a gender for adjectives)."""
    out = []
    for (case, number), (ending, mode) in table.items():
        raw = stem + ending
        form = _acc(raw, mode, stem_k)
        out.append((form, [case, number, *extra]))
    return out


# --- nouns -----------------------------------------------------------------

def _noun_os(lemma: str):
    # masculine -ος (άνθρωπος, δρόμος, λαός). Long-ending cells drop a
    # proparoxytone stress to the penult; oxytone (-ός) keeps it on the ending.
    stem = strip_tonos(lemma[:-2])
    if stress_pos(lemma) == 1:  # oxytone -ός → ending-stressed throughout
        table = {
            ("nominative", "singular"): ("ος", "ultima"),
            ("genitive", "singular"): ("ου", "ultima"),
            ("accusative", "singular"): ("ο", "ultima"),
            ("vocative", "singular"): ("ε", "ultima"),
            ("nominative", "plural"): ("οι", "ultima"),
            ("genitive", "plural"): ("ων", "ultima"),
            ("accusative", "plural"): ("ους", "ultima"),
            ("vocative", "plural"): ("οι", "ultima"),
        }
        return _emit(stem, table, 0, [])
    k = stress_index_from_start(lemma)
    # GENITIVE cells are intentionally omitted: whether the accent shifts in the
    # genitive (learned άνθρωπος→ανθρώπου vs demotic γάιδαρος→γάιδαρου) is a
    # lexical property the bare lemma can't reveal, so we'd be guessing on the
    # largest, most-consulted cells. Wiktionary stays the source for -ος
    # genitives; we generate only the accent-stable nom/acc/voc.
    table = {
        ("nominative", "singular"): ("ος", "stem"),
        ("accusative", "singular"): ("ο", "stem"),
        ("vocative", "singular"): ("ε", "stem"),
        ("nominative", "plural"): ("οι", "stem"),
        ("accusative", "plural"): ("ους", "stem"),
        ("vocative", "plural"): ("οι", "stem"),
    }
    return _emit(stem, table, k, [])


def _noun_o(lemma: str):
    # neuter -ο (βιβλίο, πρόσωπο). Same accent behaviour as masc -ος in the
    # long cells; plural is -α.
    stem = strip_tonos(lemma[:-1])
    k = stress_index_from_start(lemma)
    oxy = stress_pos(lemma) == 1
    if oxy:
        table = {
            ("nominative", "singular"): ("ο", "ultima"),
            ("genitive", "singular"): ("ου", "ultima"),
            ("accusative", "singular"): ("ο", "ultima"),
            ("vocative", "singular"): ("ο", "ultima"),
            ("nominative", "plural"): ("α", "ultima"),
            ("genitive", "plural"): ("ων", "ultima"),
            ("accusative", "plural"): ("α", "ultima"),
            ("vocative", "plural"): ("α", "ultima"),
        }
        return _emit(stem, table, 0, [])
    # Same lexical genitive-shift ambiguity as -ος (νούμερο→νούμερου vs learned
    # πρόσωπο→προσώπου), worse for the many -ιο learned neuters (ωράριο→ωραρίων).
    # Omit the genitive; generate only the accent-stable nom/acc/voc.
    table = {
        ("nominative", "singular"): ("ο", "stem"),
        ("accusative", "singular"): ("ο", "stem"),
        ("vocative", "singular"): ("ο", "stem"),
        ("nominative", "plural"): ("α", "stem"),
        ("accusative", "plural"): ("α", "stem"),
        ("vocative", "plural"): ("α", "stem"),
    }
    return _emit(stem, table, k, [])


def _noun_a_fem(lemma: str):
    # feminine -α (χώρα, καρδιά, θάλασσα). gen sg adds -ς; oxytone keeps the
    # ending stress. NO genitive plural: -α fems split between -ών (χωρών) and a
    # penult -τήτων for the productive -τητα abstracts (ταχύτητα→ταχυτήτων), and
    # the bare lemma can't tell them apart — we refuse rather than emit a wrong cell.
    stem = strip_tonos(lemma[:-1])
    k = stress_index_from_start(lemma)
    oxy = stress_pos(lemma) == 1
    sg_mode = "ultima" if oxy else "stem"
    pl_mode = "ultima" if oxy else "stem"
    table = {
        ("nominative", "singular"): ("α", sg_mode),
        ("genitive", "singular"): ("ας", sg_mode),
        ("accusative", "singular"): ("α", sg_mode),
        ("vocative", "singular"): ("α", sg_mode),
        ("nominative", "plural"): ("ες", pl_mode),
        ("accusative", "plural"): ("ες", pl_mode),
        ("vocative", "plural"): ("ες", pl_mode),
    }
    return _emit(stem, table, k, [])


def _noun_h_fem(lemma: str):
    # feminine -η (νίκη, ψυχή). SINGULAR ONLY: the plural is genuinely ambiguous
    # from the bare lemma — νίκη→νίκες but λέξη/πόλη/τάξη→λέξεις/πόλεις/τάξεις
    # (ancient 3rd-declension -εις/-εων), undistinguishable by ending. We refuse
    # to guess the plural rather than emit wrong forms; the regular singular
    # (-η/-ης/-η/-η) is safe.
    stem = strip_tonos(lemma[:-1])
    k = stress_index_from_start(lemma)
    mode = "ultima" if stress_pos(lemma) == 1 else "stem"
    table = {
        ("nominative", "singular"): ("η", mode),
        ("genitive", "singular"): ("ης", mode),
        ("accusative", "singular"): ("η", mode),
        ("vocative", "singular"): ("η", mode),
    }
    return _emit(stem, table, k, [])


def _noun_i_neuter(lemma: str):
    # neuter -ι (παιδί, μάτι). Inserts -ι-: gen sg -ιού, pl -ιά, gen pl -ιών.
    stem = strip_tonos(lemma[:-1])  # drop final ι; the ending re-adds it
    k = stress_index_from_start(lemma)
    oxy = stress_pos(lemma) == 1
    pl_mode = "ultima" if oxy else "stem"
    table = {
        ("nominative", "singular"): ("ι", "ultima" if oxy else "stem"),
        ("genitive", "singular"): ("ιου", "ultima"),
        ("accusative", "singular"): ("ι", "ultima" if oxy else "stem"),
        ("vocative", "singular"): ("ι", "ultima" if oxy else "stem"),
        ("nominative", "plural"): ("ια", pl_mode),
        ("genitive", "plural"): ("ιων", "ultima"),
        ("accusative", "plural"): ("ια", pl_mode),
        ("vocative", "plural"): ("ια", pl_mode),
    }
    return _emit(stem, table, k, [])


def _noun_ma_neuter(lemma: str):
    # neuter -μα (πρόβλημα → προβλήματος). nom/acc/voc SG are the lemma itself;
    # the oblique stem appends -τ- (προβλημα→προβληματ). Trisyllaby clamps gen sg
    # and nom-acc-voc pl to the antepenult; gen pl sits on the penult (-άτων).
    oblique = strip_tonos(lemma) + "τ"   # προβλημα → προβληματ
    k = stress_index_from_start(lemma)   # stem accent nucleus (from start)
    out: list[tuple[str, list[str]]] = []
    # singular nom/acc/voc = the bare lemma, accent intact
    for case in ("nominative", "accusative", "vocative"):
        out.append((lemma, [case, "singular"]))
    # oblique cells built from the -τ- stem
    oblique_table = {
        ("genitive", "singular"): ("ος", "stem_cap3"),
        ("nominative", "plural"): ("α", "stem_cap3"),
        ("genitive", "plural"): ("ων", "penult"),
        ("accusative", "plural"): ("α", "stem_cap3"),
        ("vocative", "plural"): ("α", "stem_cap3"),
    }
    for (case, number), (ending, mode) in oblique_table.items():
        raw = oblique + ending
        out.append((_acc(raw, mode, k), [case, number]))
    return out


# --- adjectives ------------------------------------------------------------

def _adj_os(lemma: str):
    # -ος adjective: three genders. -ος/-η/-ο (καλός) is the default; -ος/-α/-ο
    # (ωραίος, with a vowel before -ος) takes -α in the feminine.
    stem = strip_tonos(lemma[:-2])
    k = stress_index_from_start(lemma)
    oxy = stress_pos(lemma) == 1
    fem_vowel = "α" if (len(stem) and stem[-1] in "αεέιί") else "η"

    def col(ending_map, gender, stem_k):
        return _emit(stem, ending_map, stem_k, [gender])

    # Demotic -ος adjectives keep the stress on its lemma syllable throughout
    # (ουδέτερος→ουδέτερου, NOT the ancient ουδετέρου): every cell is "stem".
    masc = {
        ("nominative", "singular"): ("ος", "ultima" if oxy else "stem"),
        ("genitive", "singular"): ("ου", "ultima" if oxy else "stem"),
        ("accusative", "singular"): ("ο", "ultima" if oxy else "stem"),
        ("vocative", "singular"): ("ε", "ultima" if oxy else "stem"),
        ("nominative", "plural"): ("οι", "ultima" if oxy else "stem"),
        ("genitive", "plural"): ("ων", "ultima" if oxy else "stem"),
        ("accusative", "plural"): ("ους", "ultima" if oxy else "stem"),
        ("vocative", "plural"): ("οι", "ultima" if oxy else "stem"),
    }
    fmode = "ultima" if oxy else "stem"
    fem = {
        ("nominative", "singular"): (fem_vowel, fmode),
        ("genitive", "singular"): (fem_vowel + "ς", fmode),
        ("accusative", "singular"): (fem_vowel, fmode),
        ("vocative", "singular"): (fem_vowel, fmode),
        ("nominative", "plural"): ("ες", fmode),
        ("genitive", "plural"): ("ων", fmode),  # demotic keeps stem stress (ουδέτερων)
        ("accusative", "plural"): ("ες", fmode),
        ("vocative", "plural"): ("ες", fmode),
    }
    neut = {
        ("nominative", "singular"): ("ο", "ultima" if oxy else "stem"),
        ("genitive", "singular"): ("ου", "ultima" if oxy else "stem"),
        ("accusative", "singular"): ("ο", "ultima" if oxy else "stem"),
        ("vocative", "singular"): ("ο", "ultima" if oxy else "stem"),
        ("nominative", "plural"): ("α", "ultima" if oxy else "stem"),
        ("genitive", "plural"): ("ων", "ultima" if oxy else "stem"),
        ("accusative", "plural"): ("α", "ultima" if oxy else "stem"),
        ("vocative", "plural"): ("α", "ultima" if oxy else "stem"),
    }
    return col(masc, "masculine", k) + col(fem, "feminine", k) + col(neut, "neuter", k)


# --- verbs (present system, active) ----------------------------------------

def _verb(lemma: str):
    # Only the *present system* active indicative — the part that is fully
    # predictable from the present stem. The aorist/future need an unpredictable
    # stem (γράφω→έγραψα, παίζω→έπαιξα) so we deliberately do NOT generate them;
    # Wiktionary remains the source for those. Three conjugation shapes:
    #   A   -ω      (γράφω): -ω -εις -ει -ουμε -ετε -ουν
    #   B1  -άω/-ώ  (αγαπώ): -άω/ώ -άς -ά(ει) -άμε -άτε -άνε/ούν
    #   B2  -ώ      (θεωρώ): -ώ -είς -εί -ούμε -είτε -ούν
    P = ["first-person", "second-person", "third-person"]
    N = ["singular", "plural"]

    def rows(forms6, stresses=None):
        out = []
        order = [("first-person", "singular"), ("second-person", "singular"),
                 ("third-person", "singular"), ("first-person", "plural"),
                 ("second-person", "plural"), ("third-person", "plural")]
        for (p, n), f in zip(order, forms6):
            out.append((f, [p, n, "present", "indicative", "active", "imperfective"]))
        return out

    # Only conjugation A (barytone -ω: γράφω, παίζω, διαβάζω) — its present
    # system is fully predictable and accent-stable on the stem syllable. The
    # contracted -άω/-ώ verbs (B1 αγαπώ vs B2 θεωρώ) are not separable from the
    # bare lemma, so we refuse them and let Wiktionary stay their source.
    if lemma.endswith("ώ") or lemma.endswith("άω"):
        return []
    if lemma.endswith("ω"):
        st = strip_tonos(lemma[:-1])
        k = stress_index_from_start(lemma)
        raws = [st + "ω", st + "εις", st + "ει", st + "ουμε", st + "ετε", st + "ουν"]
        forms = [set_stress_from_start(r, k) for r in raws]
        return rows(forms)
    return []


# --- dispatcher ------------------------------------------------------------

def supported_classes() -> list[str]:
    return ["noun:-ος", "noun:-ο", "noun:-α", "noun:-η", "noun:-ι", "noun:-μα",
            "adj:-ος", "verb:present"]


def generate(lemma: str, pos: str | None, gender: str | None) -> list[tuple[str, list[str]]]:
    """Return [(form, feature_tags)] for `lemma`, or [] if unsupported.

    Refuses anything that isn't a single Greek word matching a known productive
    ending. Output is the FULL paradigm for the class (the caller de-dupes
    against existing Wiktionary forms and keeps only the missing cells)."""
    if not lemma or " " in lemma or "-" in lemma:
        return []  # multi-word / hyphenated → out of scope
    if any("a" <= c.lower() <= "z" for c in lemma):
        return []  # contains Latin letters → not a Greek headword
    if hiatus_ambiguous(lemma):
        return []  # γάιδαρος-class: destressing changes syllabification → unsafe
    p = (pos or "").lower()
    try:
        if p == "verb":
            return _verb(lemma)
        if p == "adj":
            if lemma.endswith("ος") or lemma.endswith("ός"):
                return _adj_os(lemma)
            return []
        if p == "noun":
            g = (gender or "").lower()
            if lemma.endswith("ος") or lemma.endswith("ός"):
                return _noun_os(lemma) if g in ("masculine", "") else []
            if lemma.endswith("μα"):
                return _noun_ma_neuter(lemma) if g in ("neuter", "") else []
            if lemma.endswith("ο") or lemma.endswith("ό"):
                return _noun_o(lemma) if g in ("neuter", "") else []
            if lemma.endswith("α") or lemma.endswith("ά"):
                return _noun_a_fem(lemma) if g == "feminine" else []
            if lemma.endswith("η") or lemma.endswith("ή"):
                return _noun_h_fem(lemma) if g == "feminine" else []
            if lemma.endswith("ι") or lemma.endswith("ί"):
                return _noun_i_neuter(lemma) if g in ("neuter", "") else []
            return []
    except Exception:
        return []  # never let a malformed lemma crash the backfill
    return []
