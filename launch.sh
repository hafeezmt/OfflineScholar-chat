#!/usr/bin/env bash
set -e
DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$DIR/venv/bin/python" "$DIR/desktop.py"
