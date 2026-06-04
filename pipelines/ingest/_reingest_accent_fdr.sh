#!/usr/bin/env bash
# One-shot re-ingest to make the #1 (accent-preserving analysis keys) and #2
# (BH-FDR significance) code changes take effect in the live DB. Faithful to the
# shipped flags recorded in HANDOFF.md (#37 pooled ±2yr; #38 skip-gram defaults).
# Fail-fast: if any step fails, the API is NOT restarted so a half-written DB is
# never served — inspect /tmp/reingest.log and re-run (every step is idempotent).
set -euo pipefail
cd /c/dev/greekDict
export PYTHONIOENCODING=utf-8
DB=data/db/lexorama.sqlite

echo "=== [$(date)] STOP API (port 8011) ==="
PID=$(powershell.exe -NoProfile -Command "(Get-NetTCPConnection -LocalPort 8011 -State Listen -ErrorAction SilentlyContinue).OwningProcess" | tr -d '\r' || true)
if [ -n "$PID" ]; then
  powershell.exe -NoProfile -Command "Stop-Process -Id $PID -Force" || true
  echo "stopped PID=$PID"
else
  echo "API not running"
fi
sleep 2

echo "=== [$(date)] Layer B: frequency_timeseries (news) ==="
python pipelines/ingest/ingest_frequency_timeseries.py --leipzig-dir data/raw --leipzig-source ell_news --db "$DB"
echo "=== [$(date)] Layer B: frequency_timeseries (parliament) ==="
python pipelines/ingest/ingest_frequency_timeseries.py --parliament-csv data/raw/Greek_Parliament_Proceedings_1989_2020.csv --db "$DB"

echo "=== [$(date)] Layer C: diachronic drift (news, pool ±2) ==="
python pipelines/ingest/ingest_diachronic.py --leipzig-dir data/raw --leipzig-source ell_news --pool-window 2 --db "$DB"
echo "=== [$(date)] Layer C: diachronic drift (parliament, pool ±2) ==="
python pipelines/ingest/ingest_diachronic.py --parliament-csv data/raw/Greek_Parliament_Proceedings_1989_2020.csv --pool-window 2 --db "$DB"

echo "=== [$(date)] Bootstrap CIs + BH-FDR (news, pool ±2) ==="
python pipelines/ingest/bootstrap_drift.py --corpus news --pool-window 2 --db "$DB"
echo "=== [$(date)] Bootstrap CIs + BH-FDR (parliament, pool ±2) ==="
python pipelines/ingest/bootstrap_drift.py --corpus parliament --pool-window 2 --db "$DB"

echo "=== [$(date)] Domain classifier (skip-gram defaults) ==="
python pipelines/ingest/classify_domains.py --db "$DB"

echo "=== [$(date)] RESTART API ==="
nohup python -m uvicorn services.api.app.main:app --host 127.0.0.1 --port 8011 --app-dir . > /tmp/api.log 2>&1 &
sleep 4
echo "=== [$(date)] DONE — all steps succeeded, API restarted ==="
