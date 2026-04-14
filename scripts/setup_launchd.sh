#!/usr/bin/env bash
# Installs (or reinstalls) the briefbot nightly launchd job on macOS.
# Run: ./scripts/setup_launchd.sh
# Remove: ./scripts/setup_launchd.sh --unload
set -euo pipefail

LABEL="com.briefbot.nightly"
PLIST_DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$PROJECT_DIR/scripts/${LABEL}.plist"

unload_only="${1:-}"

if [ "$unload_only" = "--unload" ]; then
  if launchctl list | grep -q "$LABEL"; then
    launchctl unload "$PLIST_DEST" && echo "Unloaded $LABEL"
  else
    echo "$LABEL is not loaded."
  fi
  exit 0
fi

# Ensure log dir exists (plist references it)
mkdir -p "$PROJECT_DIR/data/logs"

# Stamp the template with real paths
sed \
  -e "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
  -e "s|__HOME__|${HOME}|g" \
  "$TEMPLATE" > "$PLIST_DEST"

echo "Wrote $PLIST_DEST"

# Unload first if already loaded
if launchctl list | grep -q "$LABEL"; then
  launchctl unload "$PLIST_DEST"
  echo "Unloaded previous job"
fi

launchctl load "$PLIST_DEST"
echo "Loaded $LABEL — will run nightly at 11:59 PM."
echo ""
echo "To verify:"
echo "  launchctl list | grep briefbot"
echo ""
echo "To run immediately for testing:"
echo "  launchctl start $LABEL"
echo ""
echo "To remove:"
echo "  make unload-launchd   (or: ./scripts/setup_launchd.sh --unload)"
