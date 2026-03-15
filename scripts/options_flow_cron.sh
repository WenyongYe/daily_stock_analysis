#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/root/.openclaw/workspace/daily_stock_analysis"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/options_flow_cron.log"
PYTHON_BIN="python3"

mkdir -p "$LOG_DIR"

now_utc() {
  date -u "+%Y-%m-%d %H:%M:%S UTC"
}

# Run once with retry
MAX_RETRIES=3
attempt=1
while [ $attempt -le $MAX_RETRIES ]; do
  echo "[$(now_utc)] options_flow run attempt ${attempt}/${MAX_RETRIES}" >>"$LOG_FILE"
  if "$PYTHON_BIN" "$PROJECT_DIR/options_flow_run.py" --output report --feishu >>"$LOG_FILE" 2>&1; then
    echo "[$(now_utc)] options_flow run success on attempt ${attempt}" >>"$LOG_FILE"
    exit 0
  else
    echo "[$(now_utc)] options_flow run failed on attempt ${attempt}" >>"$LOG_FILE"
  fi
  attempt=$((attempt+1))
  sleep 5
done

exit 1
