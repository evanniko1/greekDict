"""Build manifest + schema version — makes DB/code divergence detectable.

The audit (docs/AUDIT.md, F18/F60/F63) found the shipped 1.5 GB database was not
produced by the code in this repo, and that nothing could detect it: two columns the
current code writes were NULL in 100% of rows, 61% of classifier rows sat below the
floor the current code enforces, and 91% of the recorded bootstrap CIs were gone.

Two mechanisms, because they answer different questions:

1. **The manifest** (`build_manifest`) records what *future* runs did — component,
   version, git commit, inputs and their fingerprints, params, resulting row counts.
   It cannot explain a DB built before it existed.

2. **The checks** (`check_divergence`) infer divergence from evidence *in the data*,
   which is how the audit caught this in the first place. They work on any DB,
   including one with no manifest at all.

Usage:
    python pipelines/ingest/manifest.py --db data/db/lexorama.sqlite
    python pipelines/ingest/manifest.py --db ... --json
Exit code is 1 when any check fails, so it can gate CI (#42).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

# Bump when the *shape* of the schema changes (new/removed table or column) or when
# a key's semantics change. A DB whose stamp is lower than this was built by older code.
#   1 — original shape; lemma identity was (normalized_lemma, pos)
#   2 — lemma identity is (lemma, pos); accent no longer folded into the primary key
#       (R2 / audit F21). Not migratable in place: rows lost under v1 are gone and
#       only a full re-ingest recovers them.
SCHEMA_VERSION = 2

# Fingerprinting a 1.4 GB dump with full sha256 costs minutes; head+tail+size
# detects a swapped or re-downloaded dump at negligible cost.
_FP_CHUNK = 1 << 20  # 1 MiB

DDL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS build_manifest (
    id                INTEGER PRIMARY KEY,
    component         TEXT NOT NULL,       -- e.g. 'ingest_kaikki'
    component_version TEXT,                -- component's own version string
    code_commit       TEXT,                -- git HEAD at run time
    code_dirty        INTEGER,             -- 1 if the tree had uncommitted changes
    run_at            TEXT NOT NULL,       -- ISO-8601 UTC
    inputs            TEXT,                -- json: [{path, bytes, mtime, fingerprint}]
    params            TEXT,                -- json: the run's CLI/config knobs
    row_counts        TEXT                 -- json: {table: count} after the run
);
CREATE INDEX IF NOT EXISTS idx_build_manifest_component
    ON build_manifest (component, run_at);
"""


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    cur = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'")
    if cur.fetchone() is None:
        conn.execute(
            "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
    conn.commit()


def stamp_schema_version(conn: sqlite3.Connection, version: int = SCHEMA_VERSION) -> None:
    """Set the stamp explicitly (use after a migration)."""
    ensure_tables(conn)
    conn.execute(
        "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(version),),
    )
    conn.commit()


def get_schema_version(conn: sqlite3.Connection) -> int | None:
    try:
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return int(row[0]) if row else None


def fingerprint_file(path: str) -> dict:
    """Cheap but swap-detecting fingerprint: size + mtime + sha256(head||tail)."""
    st = os.stat(path)
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read(_FP_CHUNK))
        if st.st_size > _FP_CHUNK:
            fh.seek(max(0, st.st_size - _FP_CHUNK))
            h.update(fh.read(_FP_CHUNK))
    return {
        "path": os.path.basename(path),
        "bytes": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
        "fingerprint": h.hexdigest()[:32],
    }


def git_state() -> tuple[str | None, int]:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, timeout=10
        )
        if commit.returncode != 0:
            return None, 0
        return commit.stdout.strip(), 1 if dirty.stdout.strip() else 0
    except (OSError, subprocess.SubprocessError):
        return None, 0


def _count(conn: sqlite3.Connection, table: str) -> int | None:
    try:
        return conn.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]
    except sqlite3.OperationalError:
        return None


def record_build(
    conn: sqlite3.Connection,
    component: str,
    *,
    version: str = "1",
    inputs: list[str] | None = None,
    params: dict | None = None,
    tables: list[str] | None = None,
) -> None:
    """Record that `component` just wrote to this DB. Call at the end of a run."""
    ensure_tables(conn)
    commit, dirty = git_state()
    fps = []
    for p in inputs or []:
        try:
            fps.append(fingerprint_file(p))
        except OSError:
            fps.append({"path": os.path.basename(p), "error": "unreadable"})
    counts = {t: _count(conn, t) for t in (tables or [])}
    conn.execute(
        "INSERT INTO build_manifest (component, component_version, code_commit, "
        "code_dirty, run_at, inputs, params, row_counts) VALUES (?,?,?,?,?,?,?,?)",
        (
            component,
            version,
            commit,
            dirty,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            json.dumps(fps, ensure_ascii=False),
            json.dumps(params or {}, ensure_ascii=False, default=str),
            json.dumps(counts, ensure_ascii=False),
        ),
    )
    conn.commit()


def latest_builds(conn: sqlite3.Connection) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT component, component_version, code_commit, code_dirty, run_at, "
            "inputs, params, row_counts FROM build_manifest b WHERE run_at = "
            "(SELECT MAX(run_at) FROM build_manifest WHERE component = b.component) "
            "ORDER BY component"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for r in rows:
        out.append(
            {
                "component": r[0], "version": r[1], "code_commit": r[2],
                "code_dirty": bool(r[3]), "run_at": r[4],
                "inputs": json.loads(r[5] or "[]"), "params": json.loads(r[6] or "{}"),
                "row_counts": json.loads(r[7] or "{}"),
            }
        )
    return out


# --------------------------------------------------------------------------
# Data-evidence checks. Each returns (ok, detail). These do not need a manifest —
# they detect that the data cannot have been produced by the current code.
# --------------------------------------------------------------------------

def _q1(conn: sqlite3.Connection, sql: str):
    try:
        row = conn.execute(sql).fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def _check_schema_version(conn):
    v = get_schema_version(conn)
    if v is None:
        return False, ("no schema_version stamp — this DB predates manifest tracking, "
                       "so its provenance is unknown and unverifiable")
    if v != SCHEMA_VERSION:
        return False, "schema_version=%s but code expects %s" % (v, SCHEMA_VERSION)
    return True, "schema_version=%s" % v


def _check_manifest_coverage(conn):
    """Any populated table whose producing component never recorded a build."""
    owners = {
        "ingest_kaikki": ["lemmas", "senses", "forms", "relations"],
        "build_search_index": ["search_index"],
        "classify_domains": ["lemma_domain_pred"],
        "ingest_diachronic": ["diachronic_drift", "diachronic_trajectory"],
        "bootstrap_drift": [],
        "ingest_frequency": ["frequency"],
        "ingest_collocations": ["collocations"],
        "build_gloss_index": ["gloss_index"],
    }
    recorded = {b["component"] for b in latest_builds(conn)}
    unexplained = []
    for comp, tables in owners.items():
        if comp in recorded:
            continue
        for t in tables:
            n = _count(conn, t)
            if n:
                unexplained.append("%s (%s rows, no %s build recorded)" % (t, format(n, ","), comp))
    if unexplained:
        return False, "data of unknown provenance: " + "; ".join(unexplained[:6])
    return True, "every populated table has a recorded build"


def _check_drift_columns(conn):
    """Columns the current diachronic/bootstrap code always writes."""
    problems = []
    total = _q1(conn, "SELECT COUNT(*) FROM diachronic_drift")
    if not total:
        return True, "no diachronic_drift rows"
    cps = _q1(conn, "SELECT COUNT(*) FROM diachronic_drift WHERE change_point_score IS NOT NULL")
    cpy = _q1(conn, "SELECT COUNT(*) FROM diachronic_drift WHERE change_point_year IS NOT NULL")
    if cpy and not cps:
        problems.append(
            "change_point_score NULL in 100%% of %s rows while change_point_year is set in "
            "%s — the ungated argmax shipped and the z-gate never ran (F5/F9)"
            % (format(total, ","), format(cpy, ","))
        )
    ci = _q1(conn, "SELECT COUNT(*) FROM diachronic_drift WHERE drift_ci_lo IS NOT NULL")
    boot = _q1(conn, "SELECT COUNT(*) FROM diachronic_drift WHERE drift_score_boot IS NOT NULL")
    if ci and not boot:
        problems.append(
            "drift_score_boot NULL in 100%% of rows while %s rows carry a CI — the displayed "
            "drift is a single-model estimate, not the bootstrap centre (F60)" % format(ci, ",")
        )
    if problems:
        return False, " | ".join(problems)
    return True, "drift columns consistent (%s rows)" % format(total, ",")


def _check_classifier_floor(conn):
    """Rows below the floor the current code enforces prove older code wrote them."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from classify_domains import CONF_FLOOR  # noqa: E402
    except Exception:
        return True, "classify_domains not importable; skipped"
    n = _q1(conn, "SELECT COUNT(*) FROM lemma_domain_pred WHERE source='classifier'")
    if not n:
        return True, "no classifier rows"
    below = _q1(
        conn,
        "SELECT COUNT(*) FROM lemma_domain_pred WHERE source='classifier' AND score < %r"
        % float(CONF_FLOOR),
    )
    if below:
        return False, (
            "%s of %s classifier rows (%.1f%%) are below the current CONF_FLOOR=%s — "
            "the current code could not have written them (F18)"
            % (format(below, ","), format(n, ","), 100.0 * below / n, CONF_FLOOR)
        )
    return True, "all %s classifier rows clear CONF_FLOOR=%s" % (format(n, ","), CONF_FLOOR)


def _check_zipf_scale(conn):
    """Zipf is log10(count per billion); the scale tops out near 7 for real corpora."""
    mx = _q1(conn, "SELECT MAX(zipf) FROM frequency")
    if mx is None:
        return True, "no frequency rows"
    if mx > 7.5:
        return False, (
            "MAX(zipf)=%.3f exceeds the ~7 ceiling of the Zipf scale — per-lemma counts are "
            "inflated by multi-lemma double-counting (F2)" % mx
        )
    return True, "MAX(zipf)=%.3f within scale" % mx


def _check_lemma_identity(conn):
    """A DB whose lemmas table still folds accents into the key has lost words (F21)."""
    ddl = _q1(conn, "SELECT sql FROM sqlite_master WHERE type='table' AND name='lemmas'")
    if not ddl:
        return True, "no lemmas table"
    folded = "normalized_lemma" in ddl.replace(" ", "").split("UNIQUE(")[-1] \
        if "UNIQUE(" in ddl.replace(" ", "") else False
    if folded:
        # Name the casualties concretely — the pair members that should both exist.
        pairs = [("ποτέ", "πότε"), ("νομός", "νόμος"), ("δουλεία", "δουλειά"),
                 ("χαλί", "χάλι")]
        lost = []
        for a, b in pairs:
            na = _q1(conn, "SELECT COUNT(*) FROM lemmas WHERE lemma = %r" % a) or 0
            nb = _q1(conn, "SELECT COUNT(*) FROM lemmas WHERE lemma = %r" % b) or 0
            if na == 0 and nb > 0:
                lost.append(a)
            elif nb == 0 and na > 0:
                lost.append(b)
        detail = ("lemmas is keyed on the accent-FOLDED (normalized_lemma, pos): "
                  "homographs were silently dropped at ingest (F21)")
        if lost:
            detail += " — confirmed missing: " + ", ".join(lost)
        detail += ". Not migratable in place; requires a re-ingest under schema_version 2."
        return False, detail
    return True, "lemmas keyed on the accented (lemma, pos)"


CHECKS = [
    ("schema_version", _check_schema_version),
    ("lemma_identity", _check_lemma_identity),
    ("manifest_coverage", _check_manifest_coverage),
    ("drift_columns", _check_drift_columns),
    ("classifier_floor", _check_classifier_floor),
    ("zipf_scale", _check_zipf_scale),
]


def check_divergence(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for name, fn in CHECKS:
        try:
            ok, detail = fn(conn)
        except Exception as exc:  # a broken check must not mask the others
            ok, detail = False, "check raised %s: %s" % (type(exc).__name__, exc)
        out.append({"check": name, "ok": bool(ok), "detail": detail})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Report DB build provenance and code divergence.")
    ap.add_argument("--db", default=os.path.join("data", "db", "lexorama.sqlite"))
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--stamp", action="store_true",
                    help="write the current SCHEMA_VERSION into the DB (use after a migration)")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        sys.exit("DB not found: %s" % args.db)

    conn = sqlite3.connect(args.db)
    if args.stamp:
        stamp_schema_version(conn)
        print("stamped schema_version=%s" % SCHEMA_VERSION)
        conn.close()
        return

    builds = latest_builds(conn)
    checks = check_divergence(conn)
    failed = [c for c in checks if not c["ok"]]
    conn.close()

    if args.json:
        print(json.dumps({"db": args.db, "schema_version_expected": SCHEMA_VERSION,
                          "builds": builds, "checks": checks}, ensure_ascii=False, indent=2))
    else:
        print("DB: %s" % args.db)
        print("\nRecorded builds (latest per component):")
        if not builds:
            print("  (none — this DB has no build manifest)")
        for b in builds:
            dirty = " +dirty" if b["code_dirty"] else ""
            print("  %-22s %s  commit %s%s"
                  % (b["component"], b["run_at"], (b["code_commit"] or "?")[:10], dirty))
            for i in b["inputs"]:
                print("      input %s (%s bytes) %s"
                      % (i.get("path"), format(i.get("bytes", 0), ","), i.get("fingerprint", "")))
        print("\nDivergence checks:")
        for c in checks:
            print("  [%s] %-20s %s" % ("ok" if c["ok"] else "FAIL", c["check"], c["detail"]))
        print("\n%d/%d checks passed." % (len(checks) - len(failed), len(checks)))
        if failed:
            print("\nThis database was NOT produced by the code currently in this repo.\n"
                  "Numbers served from it do not correspond to the documented methodology.\n"
                  "See BACKLOG.md (R1) and docs/AUDIT.md.")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
