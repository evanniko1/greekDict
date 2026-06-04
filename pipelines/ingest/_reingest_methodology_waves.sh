#!/usr/bin/env bash
# Overnight re-run that makes the pipeline-side methodology waves take effect:
#   #48 anchored Procrustes, #49 adaptive pooling, #44 change-point confidence,
#   #51 era-neighbour frequency floor, #43 high-K + BC CIs, #50 bootstrap-mean drift,
#   #47 calibrated/abstaining domain classifier.
# Read-side waves (#45 trends, #46 keyness) are already live and need no re-run.
#
# HEAVY: bootstrap at K=100 is ~8-10h across both axes; runs all cores. Run when idle.
# Fail-fast: API is NOT restarted if any step fails, so a half-written DB is never
# served. Every step is idempotent — fix and re-run. Logs: /tmp/waves.log
set -euo pipefail
cd /c/dev/greekDict
export PYTHONIOENCODING=utf-8
DB=data/db/lexorama.sqlite
NEWS="--leipzig-dir data/raw --leipzig-source ell_news"
PARL="--parliament-csv data/raw/Greek_Parliament_Proceedings_1989_2020.csv"

echo "=== [$(date)] STOP API (port 8011) ==="
PID=$(powershell.exe -NoProfile -Command "(Get-NetTCPConnection -LocalPort 8011 -State Listen -ErrorAction SilentlyContinue).OwningProcess" | tr -d '\r' || true)
[ -n "$PID" ] && powershell.exe -NoProfile -Command "Stop-Process -Id $PID -Force" || echo "API not running"
sleep 2

# ── Layer C: diachronic drift + trajectory + change-point + era-neighbours ──
# --pool-adaptive (#49), --neighbor-min-count 50 (#51); #44/#48 are automatic in-code.
echo "=== [$(date)] Layer C diachronic (news) ==="
python pipelines/ingest/ingest_diachronic.py $NEWS --db "$DB" \
    --pool-window 2 --pool-adaptive --pool-target 200000 --neighbor-min-count 50
echo "=== [$(date)] Layer C diachronic (parliament) ==="
python pipelines/ingest/ingest_diachronic.py $PARL --db "$DB" \
    --pool-window 2 --pool-adaptive --pool-target 200000 --neighbor-min-count 50

# ── Bootstrap CIs: K=100 + BC interval (#43) + bootstrap-mean point estimate (#50) ──
# Adaptive pooling matched to ingest so the CI tracks the point estimate.
echo "=== [$(date)] Bootstrap (news, K=100) ==="
python pipelines/ingest/bootstrap_drift.py --corpus news --db "$DB" \
    --k 100 --cap 250000 --pool-window 2 --pool-adaptive --pool-target 200000
echo "=== [$(date)] Bootstrap (parliament, K=100) ==="
python pipelines/ingest/bootstrap_drift.py --corpus parliament --db "$DB" \
    --k 100 --pool-window 2 --pool-adaptive --pool-target 200000

# ── Domain classifier: Platt calibration + abstention + per-field precision (#47) ──
echo "=== [$(date)] Domain classifier (calibrated) ==="
python pipelines/ingest/classify_domains.py --db "$DB"

echo "=== [$(date)] RESTART API ==="
nohup python -m uvicorn services.api.app.main:app --host 127.0.0.1 --port 8011 --app-dir . > /tmp/api.log 2>&1 &
sleep 4
echo "=== [$(date)] DONE — all waves materialised, API restarted ==="
