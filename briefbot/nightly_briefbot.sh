#!/usr/bin/env bash
set -euo pipefail

export TZ="America/New_York"

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
BRIEFBOT_DIR="${BRIEFBOT_DIR:-$PROJECT_DIR}"
ENV_FILE="${BRIEFBOT_ENV_FILE:-$PROJECT_DIR/.env}"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

VENV_DIR="$PROJECT_DIR/.venv"
if [ -f "$VENV_DIR/bin/activate" ]; then
  # shellcheck disable=SC1091
  . "$VENV_DIR/bin/activate"
fi

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

# Notification backend: mailgun (default), openclaw, or none
NOTIFICATION_BACKEND="${BRIEFBOT_NOTIFICATION_BACKEND:-mailgun}"

# Mailgun settings (used when NOTIFICATION_BACKEND=mailgun)
MAILGUN_SENDING_API_KEY="${MAILGUN_SENDING_API_KEY:-}"
MAILGUN_DOMAIN="${MAILGUN_DOMAIN:-}"
BRIEFBOT_EMAIL_TO="${BRIEFBOT_EMAIL_TO:-}"
BRIEFBOT_EMAIL_FROM="${BRIEFBOT_EMAIL_FROM:-briefbot@${MAILGUN_DOMAIN}}"

# OpenClaw / Telegram settings (used when NOTIFICATION_BACKEND=openclaw)
# Telegram target examples:
# - chat id (recommended): 123456789
# - username: @myhandle
MESSAGE_TARGET="${BRIEFBOT_TELEGRAM_TARGET:-${OPENCLAW_TELEGRAM_TARGET:-${TELEGRAM_TARGET:-}}}"
OPENCLAW_BIN="${OPENCLAW_BIN:-openclaw}"

DASHBOARD_BRIEFS_URL="${DASHBOARD_BRIEFS_URL:-}"
GREETING_NAME="${BRIEFBOT_GREETING_NAME:-there}"

mkdir -p "$LOG_DIR"
mkdir -p "$BRIEF_DIR"
mkdir -p "$CACHE_DIR"
mkdir -p "$SUMMARY_DIR"
mkdir -p "$DIGEST_DIR"

DATE_STR="$(date +%F)"
LOGFILE="$LOG_DIR/nightly.$DATE_STR.log"
LOCKFILE="$LOG_DIR/nightly.lock"

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%S%z)] $*"
}

notify_mailgun() {
  local msg="$1"
  if [ -z "${MAILGUN_SENDING_API_KEY:-}" ] || [ -z "${MAILGUN_DOMAIN:-}" ]; then
    log "NOTICE: Mailgun notification skipped; MAILGUN_SENDING_API_KEY or MAILGUN_DOMAIN not set."
    return 0
  fi
  if [ -z "${BRIEFBOT_EMAIL_TO:-}" ]; then
    log "NOTICE: Mailgun notification skipped; BRIEFBOT_EMAIL_TO not set."
    return 0
  fi
  local from="${BRIEFBOT_EMAIL_FROM:-briefbot@${MAILGUN_DOMAIN}}"
  local subject="Briefbot: Daily Brief for ${DATE_STR}"
  local mailgun_base="${MAILGUN_API_BASE:-https://api.mailgun.net/v3}"
  local response_file
  response_file="$(mktemp)"
  log "Sending email notification via Mailgun to ${BRIEFBOT_EMAIL_TO}"
  local http_code
  http_code=$(curl -s -o "$response_file" -w "%{http_code}" \
    --user "api:${MAILGUN_SENDING_API_KEY}" \
    "${mailgun_base}/${MAILGUN_DOMAIN}/messages" \
    -F "from=${from}" \
    -F "to=${BRIEFBOT_EMAIL_TO}" \
    -F "subject=${subject}" \
    -F "text=${msg}")
  if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
    log "Mailgun email sent (HTTP $http_code)"
  else
    log "WARNING: Mailgun email failed (HTTP $http_code): $(cat "$response_file")"
  fi
  rm -f "$response_file"
}

notify_openclaw() {
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

notify() {
  local msg="$1"
  case "${NOTIFICATION_BACKEND}" in
    mailgun)
      notify_mailgun "$msg"
      ;;
    openclaw)
      notify_openclaw "$msg"
      ;;
    none)
      log "NOTICE: Notifications disabled (BRIEFBOT_NOTIFICATION_BACKEND=none)"
      ;;
    *)
      log "WARNING: Unknown BRIEFBOT_NOTIFICATION_BACKEND '${NOTIFICATION_BACKEND}'; skipping notification."
      ;;
  esac
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
  log "Env file: $ENV_FILE"
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
  run_step "compose brief" python3 - <<PY
import os
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None
if load_dotenv:
    load_dotenv(dotenv_path=os.getenv("BRIEFBOT_ENV_FILE", "${ENV_FILE}"))
from briefbot.brief import write_daily_brief
path = write_daily_brief(
    date_str="${DATE_STR}",
    digest_dir="${DIGEST_DIR}",
    out_dir="${BRIEF_DIR}",
    db_path="${DB_PATH}",
)
print(path)
PY

  local brief_path="$BRIEF_DIR/$DATE_STR.daily.md"
  log "Listing brief dir after compose:"
  ls -lah "$BRIEF_DIR" || true
  log "Looking for expected brief file:"
  find "$BRIEF_DIR" -maxdepth 1 -type f -name "$DATE_STR.daily.md" -print || true
  if [ ! -f "$brief_path" ]; then
    log "ERROR: expected brief file was not created: $brief_path"
    return 1
  fi

  local message="✅ Good morning ${GREETING_NAME}! Your daily brief is ready to view."
  if [ -n "${DASHBOARD_BRIEFS_URL:-}" ]; then
    message="${message}

${DASHBOARD_BRIEFS_URL}"
  fi
  notify "$message"

  log "OK: wrote $brief_path"
}

# Prevent overlap and keep output visible in both console and logfile.
if ! mkdir "$LOCKFILE" 2>/dev/null; then
  log "Another nightly run is already in progress: $LOCKFILE"
  exit 1
fi
trap 'rm -rf "$LOCKFILE"' EXIT

exec > >(tee -a "$LOGFILE") 2>&1
trap 'on_error "$?"' ERR

run
