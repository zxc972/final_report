#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
MODULE_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"

exec bash "$MODULE_DIR/ACPC_Alignment.sh" "$@"
