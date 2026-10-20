#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
MODULE_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"

cd "$MODULE_DIR/monkey-brain-frontend" || exit 1
exec bash "$MODULE_DIR/monkey-brain-frontend/start-gui-stack.sh" "$@"
