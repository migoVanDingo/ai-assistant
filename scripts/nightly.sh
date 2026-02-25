#!/usr/bin/env bash
set -euo pipefail

# --- config ---
TZ="America/New_York"
export TZ

BRIEFBOT_DIR="${BRIEFBOT_DIR:-$HOME/briefbot}"
DB_PATH="${BRIEFBOT_DB_PATH:-$BRIEFBOT_DIR/data/briefbot.db}"
BRIEF_DIR="${BRIEFBOT_BRIEF_DIR:-$BRIEFBOT_DIR/data/briefs}"
LOG_DIR="${BRIEFBOT_LOG_DIR:-$BRIEFBOT_DIR/data/logs}"
mkdir -p "$LOG_DIR"

# Lock so cron can’t overlap if something stalls
LOCKFILE="$LOG_DIR/nightly.lock"

# Choose the brief date.
# Running at 11pm means "today" becomes the brief you read tomorrow morning.
DATE_STR="$(date +%F)"

run() {
  cd "$BRIEFBOT_DIR"

  echo "=== $(date -Is) Nightly briefbot run for $DATE_STR ==="

  # Full pipeline
  python3 -m briefbot collect
  python3 -m briefbot cluster --date "$DATE_STR" --window-days 14
  python3 -m briefbot topics --date "$DATE_STR" --window-days 30 --limit 50
  python3 -m briefbot export --date "$DATE_STR" --view balanced --limit 50
  python3 -m briefbot export --date "$DATE_STR" --view trends --limit 50
  python3 -m briefbot export --date "$DATE_STR" --view opportunities --limit 50
  python3 -m briefbot export --date "$DATE_STR" --view followups --limit 50
  python3 -m briefbot export --date "$DATE_STR" --view topics --limit 50
  python3 -m briefbot morning-brief --date "$DATE_STR" --window-days 14 --limit 50

  BRIEF_PATH="$BRIEF_DIR/$DATE_STR.daily.md"

  # Quick “headline” for notification (grab Today’s Moves if present, else top header)
  MOVES="$(awk '
    BEGIN{in=0}
    /^## Today/ {in=1; next}
    in==1 && /^## / {exit}
    in==1 {print}
  ' "$BRIEF_PATH" | sed '/^\s*$/d' | head -n 12)"

  if [ -z "$MOVES" ]; then
    MOVES="$(head -n 12 "$BRIEF_PATH")"
  fi

  # Notify yourself via OpenClaw:
  # 1) Message your OpenClaw agent (prints response; useful for logs)
  openclaw agent --agent main -m "✅ New Briefbot brief ready: $DATE_STR. File: $BRIEF_PATH

$MOVES" --json >/dev/null || true

  echo "OK: wrote $BRIEF_PATH"
}

# Use flock if available (Linux); fallback to naive lock.
if command -v flock >/dev/null 2>&1; then
  flock -n "$LOCKFILE" bash -lc run >>"$LOG_DIR/nightly.$DATE_STR.log" 2>&1
else
  if [ -e "$LOCKFILE" ]; then
    echo "Lock exists; exiting."
    exit 0
  fi
  touch "$LOCKFILE"
  trap 'rm -f "$LOCKFILE"' EXIT
  run >>"$LOG_DIR/nightly.$DATE_STR.log" 2>&1
fi