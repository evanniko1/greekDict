"""Tests for pooled / larger slice training (#37). Run: pytest tests/ -q

`_pool_members(center, years, window)` selects the ±window band of adjacent years
(same corpus/axis) that get pooled into one slice's training data, so thin years
borrow sentences from their neighbors and rare-word vectors stabilize. The model
is still labeled by its CENTRE year, so drift/trajectory semantics are unchanged.

`_pooled_to_tempfile(paths, cap, tmp_dir)` concatenates member files into one temp
training file, uniform-reservoir-sampled down to `cap` lines when they exceed it.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest"))

from ingest_diachronic import (  # noqa: E402
    _pool_members, _pooled_to_tempfile, _adaptive_members,
)

YEARS = [2011, 2012, 2013, 2014, 2015, 2016]


def test_window_zero_is_single_year():
    # No pooling: a 0 window must yield exactly the centre year.
    assert _pool_members(2013, YEARS, 0) == [2013]


def test_window_two_is_five_year_band():
    # ±2 around an interior year = the full 5-year band, sorted.
    assert _pool_members(2013, YEARS, 2) == [2011, 2012, 2013, 2014, 2015]


def test_band_clips_at_corpus_edges():
    # Near the first year the band is asymmetric — only existing years are pooled,
    # never inventing slices outside the corpus span.
    assert _pool_members(2011, YEARS, 2) == [2011, 2012, 2013]
    assert _pool_members(2016, YEARS, 2) == [2014, 2015, 2016]


def test_band_ignores_missing_interior_years():
    # A gap in the materialized years (e.g. a corpus missing 2013) is simply absent
    # from the band rather than faked.
    sparse = [2011, 2012, 2014, 2015]
    assert _pool_members(2013, sparse, 2) == [2011, 2012, 2014, 2015]


def test_pooled_tempfile_concatenates_uncapped(tmp_path):
    a = tmp_path / "a.txt"; a.write_text("l1\nl2\n", encoding="utf-8")
    b = tmp_path / "b.txt"; b.write_text("l3\n", encoding="utf-8")
    out = _pooled_to_tempfile([str(a), str(b)], cap=0, tmp_dir=str(tmp_path))
    try:
        with open(out, encoding="utf-8") as fh:
            lines = fh.readlines()
        assert sorted(l.strip() for l in lines) == ["l1", "l2", "l3"]
    finally:
        os.remove(out)


def test_pooled_tempfile_caps_line_count(tmp_path):
    import random
    random.seed(0)
    big = tmp_path / "big.txt"
    big.write_text("".join(f"line{i}\n" for i in range(1000)), encoding="utf-8")
    out = _pooled_to_tempfile([str(big)], cap=100, tmp_dir=str(tmp_path))
    try:
        with open(out, encoding="utf-8") as fh:
            lines = fh.readlines()
        assert len(lines) == 100  # reservoir bounds the pooled corpus
        assert all(l.startswith("line") for l in lines)  # real sentences, no corruption
    finally:
        os.remove(out)


# ── adaptive pooling window (#49) ────────────────────────────────────────────

def test_adaptive_dense_year_stays_unpooled():
    # A year that already meets the target on its own keeps window 0 (full resolution).
    lc = {y: 50_000 for y in YEARS}
    lc[2013] = 250_000  # dense
    assert _adaptive_members(2013, YEARS, lc, target=200_000, max_window=2) == [2013]


def test_adaptive_thin_year_expands_until_target():
    # A thin year borrows just enough neighbours to clear the target.
    lc = {y: 60_000 for y in YEARS}  # need 4 slices (240k) to clear 200k
    members = _adaptive_members(2013, YEARS, lc, target=200_000, max_window=2)
    # ±1 = 3 slices = 180k (<200k); ±2 = 5 slices = 300k (≥200k) → window 2
    assert members == [2011, 2012, 2013, 2014, 2015]


def test_adaptive_caps_at_max_window():
    # Even if the target is never reached, the window never exceeds max_window.
    lc = {y: 1_000 for y in YEARS}
    members = _adaptive_members(2013, YEARS, lc, target=10_000_000, max_window=1)
    assert members == [2012, 2013, 2014]


def test_adaptive_window_zero_or_no_target_is_single_year():
    lc = {y: 1 for y in YEARS}
    assert _adaptive_members(2013, YEARS, lc, target=0, max_window=2) == [2013]
    assert _adaptive_members(2013, YEARS, lc, target=100, max_window=0) == [2013]
