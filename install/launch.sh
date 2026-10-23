#!/usr/bin/env bash
set -e
DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -P "$DIR/.." && pwd)"
cd "$ROOT"
exec "$ROOT/venv/bin/python" -m offlinescholar.desktop
