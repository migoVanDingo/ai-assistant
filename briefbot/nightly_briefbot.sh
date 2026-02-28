#!/usr/bin/env bash
set -euo pipefail

export TZ="America/New_York"

PROJECT_DIR="${PROJECT_DIR:-/home/node1/Projects/ai-assistant}"
BRIEFBOT_DIR="${BRIEFBOT_DIR:-$PROJECT_DIR}"
DATA_DIR="${BRIEFBOT_DATA_DIR:-$PROJECT_DIR/data}"
BRIEF_DIR="${BRIEFBOT_BRIEF_DIR:-$DATA_DIR/briefs}"
LOG_DIR="${BRIEFBOT_LOG_DIR:-$DATA_DIR/logs}"
DB_PATH="${BRIEFBOT_DB_PATH:-$DATA_DIR/briefbot.db}"
CACHE_DIR="${BRIEFBOT_CACHE_DIR:-$DATA_DIR/article_cache}"
SUMMARY_DIR="${BRIEFBOT_SUMMARY_DIR:-$DATA_DIR/summaries}"
DIGEST_DIR="${BRIEFBOT_DIGEST_DIR:-$DATA_DIR/daily_digest}"

export BRIEFBOT_BRIEF_DIR="$BRIEF_DIR"
export BRIEFBOT_LOG_DIR="$LOG_DIR"
export BRIEFBOT_DB_PATH="$DB_PATH"
export BRIEFBOT_CACHE_DIR="$CACHE_DIR"
export BRIEFBOT_SUMMARY_DIR="$SUMMARY_DIR"

# Telegram target examples:
# - chat id (recommended): 123456789
# - username: @myhandle
TELEGRAM_TARGET="${BRIEFBOT_TELEGRAM_TARGET:-}"

mkdir -p "$LOG_DIR"
mkdir -p "$BRIEF_DIR"
mkdir -p "$CACHE_DIR"
mkdir -p "$SUMMARY_DIR"
mkdir -p "$DIGEST_DIR"

DATE_STR="$(date +%F)"
LOGFILE="$LOG_DIR/nightly.$DATE_STR.log"
LOCKFILE="$LOG_DIR/nightly.lock"

log() {
  echo "[$(date -Is)] $*"
}

notify() {
  local msg="$1"
  if [ -n "${TELEGRAM_TARGET:-}" ]; then
    openclaw message send --channel telegram --target "$TELEGRAM_TARGET" --message "$msg" >/dev/null 2>&1 || true
  fi
}

on_error() {
  local exit_code="${1:-1}"
  log "ERROR: nightly briefbot run failed with exit code $exit_code"
  log "Project dir: $PROJECT_DIR"
  log "DB path: $DB_PATH"
  log "Brief dir: $BRIEF_DIR"
  log "Log file: $LOGFILE"
  notify "⚠️ Briefbot nightly failed for $DATE_STR (exit=$exit_code). See log: $LOGFILE"
}

run_step() {
  local label="$1"
  shift
  log "START: $label"
  "$@"
  log "DONE: $label"
}

run() {
  cd "$BRIEFBOT_DIR"

  log "=== Briefbot nightly run for $DATE_STR ==="
  log "Project dir: $PROJECT_DIR"
  log "Runtime dir: $BRIEFBOT_DIR"
  log "DB path: $DB_PATH"
  log "Digest dir: $DIGEST_DIR"
  log "Brief dir: $BRIEF_DIR"
  log "Summary dir: $SUMMARY_DIR"
  log "Cache dir: $CACHE_DIR"

  run_step "collect" python3 -m briefbot --db "$DB_PATH" collect
  run_step "cluster" python3 -m briefbot --db "$DB_PATH" cluster --date "$DATE_STR" --window-days 14
  run_step "topics" python3 -m briefbot --db "$DB_PATH" topics --date "$DATE_STR" --window-days 30 --limit 50

  # Export views + compose brief
  run_step "export balanced" python3 -m briefbot --db "$DB_PATH" export --date "$DATE_STR" --view balanced --limit 50
  run_step "export trends" python3 -m briefbot --db "$DB_PATH" export --date "$DATE_STR" --view trends --limit 50
  run_step "export opportunities" python3 -m briefbot --db "$DB_PATH" export --date "$DATE_STR" --view opportunities --limit 50
  run_step "export followups" python3 -m briefbot --db "$DB_PATH" export --date "$DATE_STR" --view followups --limit 50
  run_step "export topics" python3 -m briefbot --db "$DB_PATH" export --date "$DATE_STR" --view topics --limit 50
  run_step "compose brief" python3 -m briefbot --db "$DB_PATH" morning-brief --date "$DATE_STR" --window-days 14 --limit 50

  local brief_path="$BRIEF_DIR/$DATE_STR.daily.md"
  if [ ! -f "$brief_path" ]; then
    log "ERROR: expected brief file was not created: $brief_path"
    return 1
  fi

  # Extract Today’s Moves (if present) for the notification body
  local moves
  moves="$(awk '
    BEGIN{in=0}
    /^## Today/ {in=1; next}
    in==1 && /^## / {exit}
    in==1 {print}
  ' "$brief_path" | sed '/^\s*$/d' | head -n 12)"

  if [ -z "${moves:-}" ]; then
    moves="(No Today’s Moves section found.)"
  fi

  notify "✅ New Briefbot brief is ready: $DATE_STR

$moves

File: $brief_path"

  log "OK: wrote $brief_path"
}

# Prevent overlap and keep output visible in both console and logfile.
exec 9>"$LOCKFILE"
if ! flock -n 9; then
  log "Another nightly run is already in progress: $LOCKFILE"
  exit 1
fi

exec > >(tee -a "$LOGFILE") 2>&1
trap 'on_error "$?"' ERR

run
