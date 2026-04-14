#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
DASHBOARD_DIR="$PROJECT_DIR/dashboard"
LOG_DIR="${LOG_DIR:-$PROJECT_DIR/data/logs}"
LOCAL="${LOCAL:-0}"
if [ "$LOCAL" = "1" ]; then
  API_PORT="${API_PORT:-59101}"
  FRONTEND_PORT="${FRONTEND_PORT:-59100}"
  FRONTEND_BASE="${FRONTEND_BASE:-/}"
  API_HOST="${API_HOST:-localhost}"
  FRONTEND_HOST="${FRONTEND_HOST:-localhost}"
else
  API_PORT="${API_PORT:-59001}"
  FRONTEND_PORT="${FRONTEND_PORT:-59000}"
  FRONTEND_BASE="${FRONTEND_BASE:-/briefs/}"
  API_HOST="${API_HOST:-127.0.0.1}"
  FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
fi
PYTHON_BIN="${PYTHON_BIN:-$PROJECT_DIR/.venv/bin/python}"
PIP_BIN="${PIP_BIN:-$PROJECT_DIR/.venv/bin/pip}"
UVICORN_BIN="${UVICORN_BIN:-$PROJECT_DIR/.venv/bin/uvicorn}"
BACKEND_PID_FILE="$LOG_DIR/dashboard-api.pid"
FRONTEND_PID_FILE="$LOG_DIR/dashboard-frontend.pid"
BACKEND_LOG_FILE="$LOG_DIR/dashboard-api.log"
FRONTEND_LOG_FILE="$LOG_DIR/dashboard-frontend.log"
mkdir -p "$LOG_DIR"

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%S%z)] $*"
}

kill_pidfile() {
  local file="$1"
  if [ -f "$file" ]; then
    local pid
    pid="$(cat "$file")"
    if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
      sleep 1
    fi
    rm -f "$file"
  fi
}

resolve_public_url() {
  if [ -n "${DASHBOARD_PUBLIC_URL:-}" ]; then
    printf '%s' "$DASHBOARD_PUBLIC_URL"
    return 0
  fi
  if command -v tailscale >/dev/null 2>&1; then
    tailscale status --json 2>/dev/null | "$PYTHON_BIN" -c '
import json, sys
try:
    data = json.load(sys.stdin)
    name = (data.get("Self") or {}).get("DNSName") or ""
    if name:
        print("https://" + name.rstrip("."))
except Exception:
    pass
' || true
  fi
}

extract_bundle_path() {
  "$PYTHON_BIN" - <<PY
from pathlib import Path
import re
text = Path(r"$DASHBOARD_DIR/dist/index.html").read_text(encoding='utf-8')
match = re.search(r'src="([^"]*assets/[^"]+\.js)"', text)
if not match:
    raise SystemExit('could not find built JS bundle in dist/index.html')
print(match.group(1))
PY
}

verify_bundle_strings() {
  local bundle_rel="$1"
  local bundle_path="$DASHBOARD_DIR/dist/${bundle_rel#${FRONTEND_BASE}}"
  [ -f "$bundle_path" ] || { echo "bundle not found: $bundle_path"; return 1; }
  grep -E '/api/metrics|/api/briefs|/api/query' "$bundle_path" >/dev/null
  if grep -E '"/metrics"|"/query"' "$bundle_path" >/dev/null; then
    echo "found non-prefixed API endpoint in bundle: $bundle_path"
    return 1
  fi
  grep -F "$BUILD_SHA" "$bundle_path" >/dev/null || {
    echo "build sha not embedded in bundle: $bundle_path"
    return 1
  }
}

cd "$PROJECT_DIR"

if [ "${DEPLOY_PULL:-0}" = "1" ]; then
  log "Pulling latest changes"
  git pull --ff-only
fi

BUILD_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
BUILD_TIME="$(date -u +%FT%TZ)"

log "Installing Python dependencies"
"$PIP_BIN" install -r requirements.txt

log "Installing dashboard frontend dependencies"
npm --prefix "$DASHBOARD_DIR" install

log "Building dashboard frontend"
if [ "$LOCAL" = "1" ]; then
  VITE_API_BASE_URL="http://${API_HOST}:${API_PORT}"
else
  VITE_API_BASE_URL=''
fi
VITE_APP_BASE="$FRONTEND_BASE" VITE_BUILD_SHA="$BUILD_SHA" VITE_BUILD_TIME="$BUILD_TIME" VITE_API_BASE_URL="$VITE_API_BASE_URL" npm --prefix "$DASHBOARD_DIR" run build

BUNDLE_REL="$(extract_bundle_path)"
log "Built JS bundle: $BUNDLE_REL"
verify_bundle_strings "$BUNDLE_REL"

API_LABEL="com.briefbot.dashboard-api"
FRONTEND_LABEL="com.briefbot.dashboard-frontend"
LAUNCHD_MANAGED=0
if launchctl list 2>/dev/null | grep -q "$API_LABEL"; then
  LAUNCHD_MANAGED=1
fi

if [ "$LAUNCHD_MANAGED" = "1" ]; then
  log "Restarting launchd-managed dashboard services"
  launchctl kickstart -k "gui/$(id -u)/$API_LABEL" 2>/dev/null || launchctl stop "$API_LABEL" && launchctl start "$API_LABEL"
  launchctl kickstart -k "gui/$(id -u)/$FRONTEND_LABEL" 2>/dev/null || launchctl stop "$FRONTEND_LABEL" && launchctl start "$FRONTEND_LABEL"
  sleep 2
else
  kill_pidfile "$BACKEND_PID_FILE"
  kill_pidfile "$FRONTEND_PID_FILE"

  log "Starting dashboard backend on $API_HOST:$API_PORT"
  nohup "$UVICORN_BIN" dashboard.backend.api:app --host "$API_HOST" --port "$API_PORT" >"$BACKEND_LOG_FILE" 2>&1 &
  echo $! > "$BACKEND_PID_FILE"
  sleep 2

  log "Starting dashboard static frontend on $FRONTEND_HOST:$FRONTEND_PORT"
  nohup "$PYTHON_BIN" -m dashboard.backend.static_server --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" --dir "$DASHBOARD_DIR/dist" >"$FRONTEND_LOG_FILE" 2>&1 &
  echo $! > "$FRONTEND_PID_FILE"
  sleep 1
fi

log "Verifying local backend"
curl -fsS "http://$API_HOST:$API_PORT/api/health" >/dev/null
curl -fsS "http://$API_HOST:$API_PORT/api/metrics" >/dev/null

log "Verifying served HTML references built bundle"
SERVED_HTML="$(curl -fsS "http://$FRONTEND_HOST:$FRONTEND_PORT/")"
printf '%s' "$SERVED_HTML" | grep -F "$BUNDLE_REL" >/dev/null

PUBLIC_URL=""
if [ "$LOCAL" != "1" ]; then
  PUBLIC_URL="$(resolve_public_url || true)"
fi
if [ -n "$PUBLIC_URL" ]; then
  log "Verifying tailscale public API endpoint: $PUBLIC_URL/api/metrics"
  code="$(curl -ksS -o /dev/null -w '%{http_code}' "$PUBLIC_URL/api/metrics")"
  [ "$code" = "200" ] || { echo "expected 200 from $PUBLIC_URL/api/metrics, got $code"; exit 1; }
  log "Verifying tailscale public HTML references built bundle"
  PUBLIC_HTML="$(curl -ksS "$PUBLIC_URL${FRONTEND_BASE%/}")"
  printf '%s' "$PUBLIC_HTML" | grep -F "$BUNDLE_REL" >/dev/null
  log "Verifying public JS bundle contains /api routes"
  curl -ksS "$PUBLIC_URL$BUNDLE_REL" | grep -E '/api/metrics|/api/briefs|/api/query' >/dev/null
  if curl -ksS "$PUBLIC_URL$BUNDLE_REL" | grep -E '"/metrics"|"/query"' >/dev/null; then
    echo "public bundle contains non-prefixed API endpoints: $PUBLIC_URL$BUNDLE_REL"
    exit 1
  fi
fi

log "Dashboard deploy complete"
log "Build SHA: $BUILD_SHA"
log "Backend log: $BACKEND_LOG_FILE"
log "Frontend log: $FRONTEND_LOG_FILE"
