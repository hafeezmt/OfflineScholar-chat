#!/usr/bin/env bash
# Open OfflineScholar in its own app window, starting the local service if needed.
set -euo pipefail

URL="http://127.0.0.1:${OS_PORT:-7860}"

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user start offlinescholar >/dev/null 2>&1 || true
fi

for _ in $(seq 1 60); do
  if curl -fsS "$URL/api/status" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

if ! curl -fsS "$URL/api/status" >/dev/null 2>&1; then
  if command -v notify-send >/dev/null 2>&1; then
    notify-send "OfflineScholar" "The local server did not start. Run: systemctl --user status offlinescholar"
  fi
  exit 1
fi

if flatpak info com.google.Chrome >/dev/null 2>&1; then
  exec flatpak run com.google.Chrome --app="$URL"
fi

for browser in google-chrome chromium chromium-browser; do
  if command -v "$browser" >/dev/null 2>&1; then
    exec "$browser" --app="$URL"
  fi
done

exec xdg-open "$URL"
