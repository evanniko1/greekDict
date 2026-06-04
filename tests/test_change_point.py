"""Tests for the diachronic change-point detector (#35 + #44). Run: pytest tests/ -q

`change_point_year` takes a distance-from-reference trajectory [(year, distance)]
(first element = reference slice, distance 0) and returns `(year, confidence)`:
the year ENTERING the steepest single-step rise, scanning ONLY among comparison
slices. The reference→first step is skipped (distance jumps 0→~0.3+ from
independent-model variance alone).

#44: the winning step is now scored against the robust spread (median/MAD, with an
absolute noise floor) of the OTHER steps; a year is reported only when that z-score
≥ 2, otherwise the change point is suppressed (None) as indistinguishable from the
surrounding wobble. The confidence score is returned in both cases.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest"))

from ingest_diachronic import change_point_year  # noqa: E402


def test_confident_spike_on_quiet_baseline():
    # flat ~0.2 baseline, then a clear 0.46 jump into 2004 → confident, picks 2004
    series = [(2000, 0.0), (2001, 0.20), (2002, 0.22), (2003, 0.24), (2004, 0.70)]
    year, score = change_point_year(series)
    assert year == 2004
    assert score >= 2.0


def test_skips_reference_to_first_artifact():
    # The 0→0.6 reference→first jump must never be the change point; the steepest
    # COMPARISON-slice rise (into 2004) is chosen instead.
    series = [(1999, 0.0), (2000, 0.60), (2001, 0.30), (2002, 0.32),
              (2003, 0.34), (2004, 0.80)]
    year, _score = change_point_year(series)
    assert year == 2004
    assert year != 2000  # not the first comparison slice (the artifact)


def test_suppressed_when_steps_are_near_equal_noise():
    # Several similar small rises — no single step is a clear outlier → suppressed.
    series = [(2000, 0.0), (2001, 0.30), (2002, 0.33), (2003, 0.31), (2004, 0.34)]
    year, score = change_point_year(series)
    assert year is None          # #44: don't present a noisy argmax as fact
    assert score is not None      # but the score is still reported
    assert score < 2.0


def test_none_when_too_few_points():
    assert change_point_year([]) == (None, None)
    assert change_point_year([(2000, 0.0)]) == (None, None)
    # reference + one comparison slice → no interior step → cannot score
    assert change_point_year([(2000, 0.0), (2001, 0.5)]) == (None, None)
    # 3 points → only one comparison step → cannot score a winner against others
    assert change_point_year([(2000, 0.0), (2001, 0.5), (2002, 0.52)]) == (None, None)
    # 4 points → two comparison steps → scorable (the floor handles the thin baseline)
    y, s = change_point_year([(2000, 0.0), (2001, 0.5), (2002, 0.52), (2003, 0.9)])
    assert s is not None


def test_no_rise_returns_none_with_zero_score():
    # never rises among comparison slices (only falls) → no change point
    series = [(2000, 0.0), (2001, 0.5), (2002, 0.4), (2003, 0.3)]
    year, score = change_point_year(series)
    assert year is None
    assert score == 0.0
