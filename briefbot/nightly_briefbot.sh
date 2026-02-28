#!/usr/bin/env bash
set -euo pipefail

export TZ="America/New_York"

PROJECT_DIR="${PROJECT_DIR:-/home/node1/Projects/ai-assistant}"
BRIEFBOT_DIR="${BRIEFBOT_DIR:-$PROJECT_DIR}"
DATA_DIR="${BRIEFBOT_DATA_DIR:-$PROJECT_DIR/data}"
# Force the brief output into the project data directory to avoid inherited env ambiguity.
BRIEF_DIR="$DATA_DIR/briefs"
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
MESSAGE_TARGET="${BRIEFBOT_TELEGRAM_TARGET:-${OPENCLAW_TELEGRAM_TARGET:-${TELEGRAM_TARGET:-}}}"
OPENCLAW_BIN="${OPENCLAW_BIN:-openclaw}"

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
  local output=""
  if [ -z "${MESSAGE_TARGET:-}" ]; then
    log "NOTICE: Telegram notification skipped; no target configured. Set BRIEFBOT_TELEGRAM_TARGET."
    return 0
  fi
  if ! command -v "$OPENCLAW_BIN" >/dev/null 2>&1; then
    log "NOTICE: Telegram notification skipped; command not found: $OPENCLAW_BIN"
    return 0
  fi

  log "Sending Telegram notification to ${MESSAGE_TARGET}"
  if output="$("$OPENCLAW_BIN" message send --channel telegram --target "$MESSAGE_TARGET" --message "$msg" 2>&1)"; then
    log "Telegram notification sent"
    if [ -n "$output" ]; then
      echo "$output"
    fi
  else
    log "WARNING: Telegram notification failed"
    if [ -n "$output" ]; then
      echo "$output"
    fi
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

run_step_allow_failure() {
  local label="$1"
  shift
  local exit_code=0
  log "START: $label"
  set +e
  "$@"
  exit_code=$?
  set -e
  if [ "$exit_code" -eq 0 ]; then
    log "DONE: $label"
  else
    log "WARNING: $label exited with code $exit_code; continuing"
  fi
  return 0
}

run() {
  cd "$BRIEFBOT_DIR"

  log "=== Briefbot nightly run for $DATE_STR ==="
  log "pwd: $(pwd)"
  log "python3: $(command -v python3 || echo 'not found')"
  log "Project dir: $PROJECT_DIR"
  log "Runtime dir: $BRIEFBOT_DIR"
  log "DB path: $DB_PATH"
  log "Digest dir: $DIGEST_DIR"
  log "Brief dir: $BRIEF_DIR"
  log "Summary dir: $SUMMARY_DIR"
  log "Cache dir: $CACHE_DIR"

  run_step_allow_failure "collect" python3 -m briefbot --db "$DB_PATH" collect
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
  log "Listing brief dir after compose:"
  ls -lah "$BRIEF_DIR" || true
  log "Looking for expected brief file:"
  find "$BRIEF_DIR" -maxdepth 1 -type f -name "$DATE_STR.daily.md" -print || true
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
