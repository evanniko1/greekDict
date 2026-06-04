set -euo pipefail
cd /c/dev/greekDict
export PYTHONIOENCODING=utf-8
echo "=== [$(date)] STOP API ==="
PID=$(powershell.exe -NoProfile -Command "(Get-NetTCPConnection -LocalPort 8011 -State Listen -ErrorAction SilentlyContinue).OwningProcess" | tr -d '\r' || true)
[ -n "$PID" ] && powershell.exe -NoProfile -Command "Stop-Process -Id $PID -Force" || true
sleep 2
echo "=== [$(date)] classify_domains ==="
python pipelines/ingest/classify_domains.py --db data/db/lexorama.sqlite
echo "=== [$(date)] RESTART API ==="
nohup python -m uvicorn services.api.app.main:app --host 127.0.0.1 --port 8011 --app-dir . > /tmp/api.log 2>&1 &
sleep 4
echo "=== [$(date)] DONE classifier + API restarted ==="
