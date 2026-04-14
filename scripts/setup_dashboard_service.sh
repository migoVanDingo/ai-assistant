#!/usr/bin/env bash
# Installs (or reinstalls) the briefbot dashboard launchd services on macOS.
# Run:    ./scripts/setup_dashboard_service.sh
# Remove: ./scripts/setup_dashboard_service.sh --unload
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABELS=(com.briefbot.dashboard-api com.briefbot.dashboard-frontend)

unload_only="${1:-}"

if [ "$unload_only" = "--unload" ]; then
  for label in "${LABELS[@]}"; do
    dest="$HOME/Library/LaunchAgents/${label}.plist"
    if launchctl list | grep -q "$label"; then
      launchctl unload "$dest" && echo "Unloaded $label"
    else
      echo "$label is not loaded."
    fi
  done
  exit 0
fi

mkdir -p "$PROJECT_DIR/data/logs"

for label in "${LABELS[@]}"; do
  template="$PROJECT_DIR/scripts/${label}.plist"
  dest="$HOME/Library/LaunchAgents/${label}.plist"

  sed \
    -e "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
    -e "s|__HOME__|${HOME}|g" \
    "$template" > "$dest"

  echo "Wrote $dest"

  if launchctl list | grep -q "$label"; then
    launchctl unload "$dest"
    echo "Unloaded previous $label"
  fi

  launchctl load "$dest"
  echo "Loaded $label"
done

echo ""
echo "Dashboard services are running and will restart on login."
echo ""
echo "  Backend:  http://127.0.0.1:59001/api/health"
echo "  Frontend: http://127.0.0.1:59000"
echo ""
echo "To check status:"
echo "  launchctl list | grep briefbot"
echo ""
echo "To remove services:"
echo "  make unload-dashboard-service"
