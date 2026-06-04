"""Tests for Leipzig corpus-source discovery (#40 — additional corpora on their own
axes). Run: pytest tests/ -q

The cardinal rule is that distinct corpora stay on SEPARATE axes and never merge.
Leipzig (Wortschatz) folders are named `<source>_<YYYY>_<size>` and several Greek
corpora (news, wikipedia, web…) can sit side-by-side under one directory. These
tests pin the name parsing, the clean axis-label mapping, and — most importantly —
that `discover_leipzig_slices(root, source=…)` returns ONLY the requested corpus so
a wiki folder dropped beside news folders never gets swept into the news axis.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest"))

import corpus_sources as cs  # noqa: E402


# ── name parsing ─────────────────────────────────────────────────────────────

def test_leipzig_source_and_year():
    assert cs.leipzig_source("ell_news_2020_1M") == "ell_news"
    assert cs.leipzig_year("ell_news_2020_1M") == 2020
    assert cs.leipzig_source("ell_wikipedia_2021_1M") == "ell_wikipedia"
    assert cs.leipzig_year("ell_wikipedia_2021_1M") == 2021


def test_leipzig_source_hyphenated_prefix():
    # The source segment may itself contain underscores/hyphens before the year.
    assert cs.leipzig_source("ell-eu_web_2017_100K") == "ell-eu_web"
    assert cs.leipzig_year("ell-eu_web_2017_100K") == 2017


def test_leipzig_source_handles_full_path():
    assert cs.leipzig_source(os.path.join("data", "raw", "ell_news_2020_1M")) == "ell_news"


def test_leipzig_source_none_when_no_year():
    assert cs.leipzig_source("not_a_corpus_folder") is None
    assert cs.leipzig_corpus_label("not_a_corpus_folder") is None


# ── clean axis labels ────────────────────────────────────────────────────────

def test_known_labels_map_to_clean_axes():
    assert cs.leipzig_corpus_label("ell_news_2020_1M") == "news"
    assert cs.leipzig_corpus_label("ell_wikipedia_2021_1M") == "wiki"
    assert cs.leipzig_corpus_label("ell-eu_web_2017_100K") == "web"


def test_unknown_label_strips_language_tag():
    # An unrecognized source still yields a sensible axis: drop the ell-/ell_ tag.
    assert cs.leipzig_corpus_label("ell_subtitles_2019_1M") == "subtitles"


# ── discovery filtering (the cardinal-rule guard) ────────────────────────────

def _make_slice(root, name):
    """Create a minimal Leipzig folder (just the *-sentences.txt that qualifies it)."""
    folder = os.path.join(root, name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"{name}-sentences.txt"), "w", encoding="utf-8") as fh:
        fh.write("1\tμια προταση.\n")
    return folder


def test_discover_filters_by_source(tmp_path):
    root = str(tmp_path)
    _make_slice(root, "ell_news_2019_1M")
    _make_slice(root, "ell_news_2020_1M")
    _make_slice(root, "ell_wikipedia_2020_1M")
    _make_slice(root, "ell_wikipedia_2021_1M")

    # Without a source filter, every qualifying folder is returned (legacy behavior,
    # safe only when the directory holds a single corpus).
    assert len(cs.discover_leipzig_slices(root)) == 4

    # Filtering by clean label keeps the wiki folders OUT of the news axis.
    news = cs.discover_leipzig_slices(root, source="news")
    assert [y for y, _ in news] == [2019, 2020]
    assert all("ell_news" in os.path.basename(f) for _, f in news)

    wiki = cs.discover_leipzig_slices(root, source="wiki")
    assert [y for y, _ in wiki] == [2020, 2021]
    assert all("ell_wikipedia" in os.path.basename(f) for _, f in wiki)


def test_discover_accepts_raw_prefix_too(tmp_path):
    root = str(tmp_path)
    _make_slice(root, "ell_news_2020_1M")
    _make_slice(root, "ell_wikipedia_2021_1M")
    # Either the raw prefix or the clean label selects the same single corpus.
    assert len(cs.discover_leipzig_slices(root, source="ell_news")) == 1
    assert len(cs.discover_leipzig_slices(root, source="news")) == 1


def test_discover_leipzig_sources_overview(tmp_path):
    root = str(tmp_path)
    _make_slice(root, "ell_news_2019_1M")
    _make_slice(root, "ell_news_2020_1M")
    _make_slice(root, "ell_wikipedia_2021_1M")
    assert cs.discover_leipzig_sources(root) == {"news": [2019, 2020], "wiki": [2021]}
