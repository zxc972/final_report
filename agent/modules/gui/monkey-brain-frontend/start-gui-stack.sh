#!/usr/bin/env bash
set -euo pipefail

# Configure a token through PRIMX_ACCESS_TOKEN or --token; otherwise generate one per launch.
PRIMX_ACCESS_TOKEN="${PRIMX_ACCESS_TOKEN:-}"

# Parse optional CLI flags
# Usage: start-gui-stack.sh [--port <N>] [--pipeline-port <N>] [--agent-port <N>] [--host <HOST>] [--token <TOKEN>] [--same-origin-api|--direct-api]
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port|-p)            PORT="${2:?--port requires a value}";          shift 2 ;;
    --pipeline-port)      PIPELINE_PORT="${2:?--pipeline-port requires a value}"; shift 2 ;;
    --agent-port)         AGENT_PORT="${2:?--agent-port requires a value}";    shift 2 ;;
    --host)               FRONTEND_HOST="${2:?--host requires a value}"; shift 2 ;;
    --token)              PRIMX_ACCESS_TOKEN="${2:?--token requires a value}";  shift 2 ;;
    --same-origin-api)    PRIMX_SAME_ORIGIN_API=1; shift ;;
    --direct-api)         PRIMX_SAME_ORIGIN_API=0; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

export PRIMX_ACCESS_TOKEN

PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if [[ -z "$PRIMX_ACCESS_TOKEN" ]]; then
  PRIMX_ACCESS_TOKEN="$("$PYTHON_BIN" -c 'import secrets; print(secrets.token_urlsafe(32))')"
fi

find_free_port() {
  "$PYTHON_BIN" - <<'PY' "$1" "$2"
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
}

PIPELINE_PORT="${PIPELINE_PORT:-8000}"
AGENT_PORT="${AGENT_PORT:-8100}"
# Port 80 requires root/CAP_NET_BIND_SERVICE on Linux. Default to 8080.
# Override: --port 80 (with sudo), or set VITE_DEV_PORT / PORT env var.
FRONTEND_PORT="${VITE_DEV_PORT:-${PORT:-8080}}"
FRONTEND_HOST="${FRONTEND_HOST:-${VITE_DEV_HOST:-127.0.0.1}}"
PIPELINE_HOST="${PIPELINE_HOST:-127.0.0.1}"
AGENT_HOST="${AGENT_HOST:-127.0.0.1}"
PIPELINE_PORT="$(find_free_port "$PIPELINE_PORT" "$PIPELINE_HOST")"
AGENT_PORT="$(find_free_port "$AGENT_PORT" "$AGENT_HOST")"
FRONTEND_PORT="$(find_free_port "$FRONTEND_PORT" "$FRONTEND_HOST")"

export PIPELINE_PORT
export AGENT_PORT
export PIPELINE_HOST
export AGENT_HOST
export VITE_PIPELINE_PORT="${PIPELINE_PORT}"
export VITE_AGENT_BACKEND_PORT="${AGENT_PORT}"
export VITE_DEV_PORT="${FRONTEND_PORT}"
export VITE_DEV_HOST="${FRONTEND_HOST}"
export FRONTEND_PORT
export PRIMX_SAME_ORIGIN_API="${PRIMX_SAME_ORIGIN_API:-1}"

PORTS_FILE="$(cd "$(dirname "$0")" && pwd -P)/public/ports.json"
"$PYTHON_BIN" - <<'PY' "$PORTS_FILE" "$PIPELINE_PORT" "$AGENT_PORT" "$FRONTEND_PORT"
import json
import os
import sys
from pathlib import Path

ports_file = Path(sys.argv[1])
data = {
    "pipelinePort": sys.argv[2],
    "agentPort": sys.argv[3],
    "frontendPort": sys.argv[4],
}
if os.getenv("PRIMX_SAME_ORIGIN_API", "").lower() in {"1", "true", "yes", "on"}:
    data["sameOriginApi"] = True
pipeline_base_url = os.getenv("PRIMX_PIPELINE_BASE_URL", "").strip()
agent_base_url = os.getenv("PRIMX_AGENT_BASE_URL", "").strip()
if pipeline_base_url:
    data["pipelineBaseUrl"] = pipeline_base_url.rstrip("/")
if agent_base_url:
    data["agentBaseUrl"] = agent_base_url.rstrip("/")
ports_file.parent.mkdir(parents=True, exist_ok=True)
ports_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY

SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
# Only omit the port suffix for the standard HTTP port 80
PORT_SUFFIX=":${FRONTEND_PORT}"
if [[ "${FRONTEND_PORT}" == "80" ]]; then
  PORT_SUFFIX=""
fi

cat <<EOF

====================================================================
ACCESS TOKEN : ${PRIMX_ACCESS_TOKEN}
--------------------------------------------------------------------
LOCAL  : http://localhost${PORT_SUFFIX}/?token=${PRIMX_ACCESS_TOKEN}
REMOTE : http://${SERVER_IP:-<server-ip>}${PORT_SUFFIX}/?token=${PRIMX_ACCESS_TOKEN}
--------------------------------------------------------------------
PIPELINE PORT : ${PIPELINE_PORT}
AGENT PORT    : ${AGENT_PORT}
FRONTEND HOST : ${FRONTEND_HOST}
====================================================================

EOF

if [[ "${FRONTEND_HOST}" == "0.0.0.0" || "${FRONTEND_HOST}" == "::" ]]; then
  cat <<'EOF'
WARNING: The Vite development server is listening on a public interface.
Do not expose this port directly to the Internet. For production, run
`npm run build` and serve dist/ through Nginx.

EOF
fi

node "$(cd "$(dirname "$0")" && pwd -P)/../monkey-brain-backend/server.js" &
BACKEND_PID=$!

# Start agent backend in background
bash "$(cd "$(dirname "$0")" && pwd -P)/../../agent/start-agent-backend.sh" &
AGENT_PID=$!

cleanup() {
  if kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID"
  fi
  if kill -0 "$AGENT_PID" 2>/dev/null; then
    kill "$AGENT_PID"
  fi
}
trap cleanup EXIT

# Start frontend (foreground)
"$(cd "$(dirname "$0")" && pwd -P)"/start-notebook.sh
