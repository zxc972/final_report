#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
MODULE_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"

DEFAULT_PORT="${PIPELINE_PORT:-8000}"
PIPELINE_HOST="${PIPELINE_HOST:-127.0.0.1}"
PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

SELECTED_PORT="$($PYTHON_BIN - <<'PY' "$DEFAULT_PORT" "$PIPELINE_HOST"
import socket
import sys

start = int(sys.argv[1])
host = sys.argv[2]
for port in range(start, start + 50):
    sock = socket.socket()
    try:
        sock.bind((host, port))
        sock.close()
        print(port)
        sys.exit(0)
    except OSError:
        pass
print(start)
sys.exit(0)
PY
)"

export PIPELINE_PORT="$SELECTED_PORT"
export PIPELINE_HOST
echo "[pipeline-backend] listening on ${PIPELINE_HOST}:${PIPELINE_PORT}"

PORTS_FILE="$MODULE_DIR/monkey-brain-frontend/public/ports.json"
"$PYTHON_BIN" - <<'PY' "$PORTS_FILE" "$PIPELINE_PORT"
import json
import sys
from pathlib import Path

ports_file = Path(sys.argv[1])
pipeline_port = sys.argv[2]
data = {}
if ports_file.exists():
    try:
        data = json.loads(ports_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
data["pipelinePort"] = pipeline_port
ports_file.parent.mkdir(parents=True, exist_ok=True)
ports_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY

exec node "$MODULE_DIR/monkey-brain-backend/server.js" "$@"
