#!/usr/bin/env bash
set -euo pipefail

export TZ="America/New_York"

BRIEFBOT_DIR="${BRIEFBOT_DIR:-$HOME/briefbot}"
BRIEF_DIR="${BRIEFBOT_BRIEF_DIR:-$BRIEFBOT_DIR/data/briefs}"
LOG_DIR="${BRIEFBOT_LOG_DIR:-$BRIEFBOT_DIR/data/logs}"
DB_PATH="${BRIEFBOT_DB_PATH:-$BRIEFBOT_DIR/data/briefbot.db}"

# Telegram target examples:
# - chat id (recommended): 123456789
# - username: @myhandle
TELEGRAM_TARGET="${BRIEFBOT_TELEGRAM_TARGET:-}"

mkdir -p "$LOG_DIR"

DATE_STR="$(date +%F)"
LOGFILE="$LOG_DIR/nightly.$DATE_STR.log"
LOCKFILE="$LOG_DIR/nightly.lock"

notify() {
  local msg="$1"
  if [ -n "$TELEGRAM_TARGET" ]; then
    openclaw message send --channel telegram --target "$TELEGRAM_TARGET" --message "$msg" >/dev/null || true
  fi
}

run() {
  cd "$BRIEFBOT_DIR"

  echo "=== $(date -Is) Briefbot nightly run for $DATE_STR ==="
  python3 -m briefbot collect
  python3 -m briefbot cluster --date "$DATE_STR" --window-days 14
  python3 -m briefbot topics --date "$DATE_STR" --window-days 30 --limit 50

  # Export views + compose brief
  python3 -m briefbot export --date "$DATE_STR" --view balanced --limit 50
  python3 -m briefbot export --date "$DATE_STR" --view trends --limit 50
  python3 -m briefbot export --date "$DATE_STR" --view opportunities --limit 50
  python3 -m briefbot export --date "$DATE_STR" --view followups --limit 50
  python3 -m briefbot export --date "$DATE_STR" --view topics --limit 50
  python3 -m briefbot morning-brief --date "$DATE_STR" --window-days 14 --limit 50

  local brief_path="$BRIEF_DIR/$DATE_STR.daily.md"

  # Extract Today’s Moves (if present) for the notification body
  local moves
  moves="$(awk '
    BEGIN{in=0}
    /^## Today/ {in=1; next}
    in==1 && /^## / {exit}
    in==1 {print}
  ' "$brief_path" | sed '/^\s*$/d' | head -n 12)"

  if [ -z "$moves" ]; then
    moves="(No Today’s Moves section found.)"
  fi

  notify "✅ New Briefbot brief is ready: $DATE_STR

$moves

File: $brief_path"
  echo "OK: wrote $brief_path"
}

# Prevent overlap
if command -v flock >/dev/null 2>&1; then
  flock -n "$LOCKFILE" bash -lc run >>"$LOGFILE" 2>&1 || {
    notify "⚠️ Briefbot nightly failed for $DATE_STR. See log: $LOGFILE"
    exit 1
  }
else
  if [ -e "$LOCKFILE" ]; then exit 0; fi
  touch "$LOCKFILE"
  trap 'rm -f "$LOCKFILE"' EXIT
  run >>"$LOGFILE" 2>&1 || {
    notify "⚠️ Briefbot nightly failed for $DATE_STR. See log: $LOGFILE"
    exit 1
  }
fi