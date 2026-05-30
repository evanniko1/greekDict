"""Greek text normalization — the cornerstone used by ingest, indexing, and search.

The search key for any surface form is produced by `normalize()`. Two surfaces
that a Greek user would consider "the same word modulo accents/case/sigma"
MUST map to the same normalized key. Keep this function pure and total.

Folding applied (in order):
  1. Unicode NFC (canonical compose) on input.
  2. Lowercase.
  3. Strip combining marks (tonos, dialytika, polytonic breathings/iota subscript)
     via NFD decomposition.
  4. Fold final sigma ς -> σ.
  5. Collapse internal whitespace, trim.

This deliberately discards accent and case. Accent IS phonemic in Greek
(πότε "when" vs ποτέ "ever"), so the *display* lemma keeps its accents — only
the *search key* is folded. Disambiguation between accent-distinct homographs
is handled at the result-ranking layer, not here.
"""

from __future__ import annotations

import unicodedata

__all__ = ["normalize", "strip_accents", "fold_final_sigma", "greeklish_to_greek"]


def strip_accents(text: str) -> str:
    """Remove all combining marks (Mn): tonos, dialytika, polytonic diacritics."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def fold_final_sigma(text: str) -> str:
    """Fold word-final sigma (ς) to medial sigma (σ) so they share a key."""
    return text.replace("ς", "σ")


def normalize(text: str) -> str:
    """Produce the canonical search key for a Greek surface form."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    text = strip_accents(text)
    text = fold_final_sigma(text)
    text = " ".join(text.split())
    return text


# --- Greeklish fallback (M1) -------------------------------------------------
# A deliberately small, deterministic Latin->Greek table for the case where the
# GR-NLP-TOOLKIT transliterator is unavailable. This is a *candidate generator*,
# not ground truth — its output is fed back through normalize() and matched
# against the index. Digraphs first, longest-match.
_GREEKLISH_DIGRAPHS = [
    ("th", "θ"), ("ch", "χ"), ("ps", "ψ"), ("ks", "ξ"), ("ou", "ου"),
    ("ai", "αι"), ("ei", "ει"), ("oi", "οι"), ("gg", "γγ"), ("gk", "γκ"),
    ("mp", "μπ"), ("nt", "ντ"), ("ts", "τσ"), ("tz", "τζ"),
]
_GREEKLISH_SINGLE = {
    "a": "α", "b": "β", "g": "γ", "d": "δ", "e": "ε", "z": "ζ", "h": "η",
    "i": "ι", "k": "κ", "l": "λ", "m": "μ", "n": "ν", "x": "ξ", "o": "ο",
    "p": "π", "r": "ρ", "s": "σ", "t": "τ", "y": "υ", "u": "υ", "f": "φ",
    "w": "ω", "c": "κ", "j": "ι", "h": "η",
}


def greeklish_to_greek(text: str) -> str:
    """Best-effort Latin->Greek transliteration for a single candidate.

    Not authoritative: many-to-one ambiguity (η/ι/υ, ο/ω) is unavoidable here.
    Used only to widen the search candidate set.
    """
    s = text.lower()
    out: list[str] = []
    i = 0
    while i < len(s):
        matched = False
        for latin, greek in _GREEKLISH_DIGRAPHS:
            if s.startswith(latin, i):
                out.append(greek)
                i += len(latin)
                matched = True
                break
        if matched:
            continue
        out.append(_GREEKLISH_SINGLE.get(s[i], s[i]))
        i += 1
    return "".join(out)


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        print(f"{arg!r} -> key={normalize(arg)!r}  greeklish={greeklish_to_greek(arg)!r}")
