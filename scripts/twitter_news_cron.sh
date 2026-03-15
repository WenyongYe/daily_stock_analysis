#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/root/.openclaw/workspace/daily_stock_analysis"
PYTHON_BIN="/usr/bin/python3"
OPENCLAW_BIN="/usr/bin/openclaw"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/twitter_news_cron.log"
ALERT_TARGET="${TWITTER_NEWS_ALERT_TARGET:-user:ou_c464eab8d68c97f8c50212de97553ca9}"
MAX_RETRIES="${TWITTER_NEWS_MAX_RETRIES:-4}"

mkdir -p "$LOG_DIR"

send_alert() {
  local text="$1"
  "$OPENCLAW_BIN" message send \
    --channel feishu \
    --target "$ALERT_TARGET" \
    --message "$text" >/dev/null 2>&1 || true
}

now_utc() {
  date -u "+%Y-%m-%d %H:%M:%S UTC"
}

now_bjt() {
  TZ=Asia/Shanghai date "+%Y-%m-%d %H:%M:%S CST"
}

backoff_seconds() {
  case "$1" in
    1) echo 60 ;;
    2) echo 180 ;;
    3) echo 600 ;;
    *) echo 1800 ;;
  esac
}

attempt=1
while [ "$attempt" -le "$MAX_RETRIES" ]; do
  {
    echo "[$(now_utc)] twitter_news run attempt ${attempt}/${MAX_RETRIES}"
  } >>"$LOG_FILE"

  if "$PYTHON_BIN" "$PROJECT_DIR/twitter_news_run.py" --output report --feishu >>"$LOG_FILE" 2>&1; then
    {
      echo "[$(now_utc)] twitter_news run success on attempt ${attempt}"
    } >>"$LOG_FILE"

    if [ "$attempt" -gt 1 ]; then
      send_alert "✅【快讯任务恢复】北京时间 $(now_bjt) 已在第 ${attempt} 次重试成功推送。"
    fi
    exit 0
  fi

  {
    echo "[$(now_utc)] twitter_news run failed on attempt ${attempt}"
  } >>"$LOG_FILE"

  if [ "$attempt" -lt "$MAX_RETRIES" ]; then
    sleep_for="$(backoff_seconds "$attempt")"
    sleep "$sleep_for"
  fi

  attempt=$((attempt + 1))
done

send_alert "🚨【快讯任务失败】北京时间 $(now_bjt) 连续 ${MAX_RETRIES} 次执行失败，未完成推送。请检查服务器日志：${LOG_FILE}"
exit 1
