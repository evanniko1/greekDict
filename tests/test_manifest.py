"""Build manifest + divergence detection (R1 / audit F18, F60, F63).

The audit found the shipped DB was not produced by the repo's code and that nothing
could detect it. These tests pin the detector: it must fire on each signature of
divergence, and must stay quiet on a DB the current code actually produced.
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest"))
import manifest  # noqa: E402


def _checks(conn):
    return {c["check"]: c for c in manifest.check_divergence(conn)}


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    yield c
    c.close()


def test_unstamped_db_is_flagged(conn):
    """A DB with no schema_version stamp has unverifiable provenance."""
    assert _checks(conn)["schema_version"]["ok"] is False


def test_stamped_db_passes_version_check(conn):
    manifest.ensure_tables(conn)
    assert manifest.get_schema_version(conn) == manifest.SCHEMA_VERSION
    assert _checks(conn)["schema_version"]["ok"] is True


def test_stale_schema_version_is_flagged(conn):
    manifest.stamp_schema_version(conn, manifest.SCHEMA_VERSION - 1)
    c = _checks(conn)["schema_version"]
    assert c["ok"] is False
    assert str(manifest.SCHEMA_VERSION) in c["detail"]


def test_populated_table_without_a_recorded_build_is_flagged(conn):
    """The exact signature of the shipped DB: data present, no build recorded."""
    manifest.ensure_tables(conn)
    conn.execute("CREATE TABLE lemmas (id INTEGER PRIMARY KEY, lemma TEXT)")
    conn.execute("INSERT INTO lemmas (lemma) VALUES ('άνθρωπος')")
    conn.commit()
    c = _checks(conn)["manifest_coverage"]
    assert c["ok"] is False
    assert "lemmas" in c["detail"]


def test_recording_a_build_clears_the_coverage_check(conn):
    manifest.ensure_tables(conn)
    conn.execute("CREATE TABLE lemmas (id INTEGER PRIMARY KEY, lemma TEXT)")
    conn.execute("INSERT INTO lemmas (lemma) VALUES ('άνθρωπος')")
    conn.commit()
    manifest.record_build(conn, "ingest_kaikki", tables=["lemmas"])
    assert _checks(conn)["manifest_coverage"]["ok"] is True
    builds = manifest.latest_builds(conn)
    assert len(builds) == 1
    assert builds[0]["component"] == "ingest_kaikki"
    assert builds[0]["row_counts"]["lemmas"] == 1


def _drift_table(conn):
    conn.execute(
        "CREATE TABLE diachronic_drift (id INTEGER PRIMARY KEY, drift_ci_lo REAL, "
        "drift_score_boot REAL, change_point_year INTEGER, change_point_score REAL)"
    )


def test_ungated_change_point_is_flagged(conn):
    """change_point_year set while change_point_score is 100% NULL == the z-gate never ran."""
    manifest.ensure_tables(conn)
    _drift_table(conn)
    conn.executemany(
        "INSERT INTO diachronic_drift (change_point_year, change_point_score) VALUES (?, NULL)",
        [(2016,), (2016,), (2013,)],
    )
    conn.commit()
    c = _checks(conn)["drift_columns"]
    assert c["ok"] is False
    assert "change_point_score" in c["detail"]


def test_missing_bootstrap_centre_is_flagged(conn):
    manifest.ensure_tables(conn)
    _drift_table(conn)
    conn.executemany(
        "INSERT INTO diachronic_drift (drift_ci_lo, drift_score_boot) VALUES (?, NULL)",
        [(0.22,), (0.31,)],
    )
    conn.commit()
    c = _checks(conn)["drift_columns"]
    assert c["ok"] is False
    assert "drift_score_boot" in c["detail"]


def test_consistent_drift_rows_pass(conn):
    manifest.ensure_tables(conn)
    _drift_table(conn)
    conn.execute(
        "INSERT INTO diachronic_drift (drift_ci_lo, drift_score_boot, change_point_year, "
        "change_point_score) VALUES (0.22, 0.25, 2016, 2.4)"
    )
    conn.commit()
    assert _checks(conn)["drift_columns"]["ok"] is True


def test_zipf_above_scale_ceiling_is_flagged(conn):
    """MAX(zipf)=8.6 in the shipped DB; the scale tops out near 7 (F2)."""
    manifest.ensure_tables(conn)
    conn.execute("CREATE TABLE frequency (lemma_id INTEGER PRIMARY KEY, zipf REAL)")
    conn.execute("INSERT INTO frequency (lemma_id, zipf) VALUES (1, 8.615)")
    conn.commit()
    c = _checks(conn)["zipf_scale"]
    assert c["ok"] is False
    assert "8.6" in c["detail"]


def test_plausible_zipf_passes(conn):
    manifest.ensure_tables(conn)
    conn.execute("CREATE TABLE frequency (lemma_id INTEGER PRIMARY KEY, zipf REAL)")
    conn.execute("INSERT INTO frequency (lemma_id, zipf) VALUES (1, 5.2)")
    conn.commit()
    assert _checks(conn)["zipf_scale"]["ok"] is True


def test_a_broken_check_does_not_mask_the_others(conn):
    """One raising check must not abort the report."""
    bad = ("boom", lambda c: (_ for _ in ()).throw(RuntimeError("x")))
    manifest.CHECKS.append(bad)
    try:
        res = {c["check"]: c for c in manifest.check_divergence(conn)}
        assert res["boom"]["ok"] is False
        assert "RuntimeError" in res["boom"]["detail"]
        assert "schema_version" in res  # the rest still ran
    finally:
        manifest.CHECKS.remove(bad)


def test_fingerprint_detects_a_changed_file(tmp_path):
    p = tmp_path / "dump.jsonl"
    p.write_text('{"word": "άνθρωπος"}\n', encoding="utf-8")
    a = manifest.fingerprint_file(str(p))
    p.write_text('{"word": "λόγος"}\n', encoding="utf-8")
    b = manifest.fingerprint_file(str(p))
    assert a["fingerprint"] != b["fingerprint"]
