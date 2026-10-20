#!/bin/bash

# 🧠 Monkey Brain Segmentation System - Notebook Startup Script
# Similar to Jupyter Notebook startup

echo "╔════════════════════════════════════════════════════════════╗"
echo "║                                                            ║"
echo "║        🧠 Monkey Brain Segmentation System - Notebook Mode ║"
echo "║                                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed"
    echo "Please install Node.js 18+: https://nodejs.org/"
    exit 1
fi

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed"
    exit 1
fi

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 First run, installing dependencies..."
    npm install
fi

# Get local IP
if command -v hostname &> /dev/null; then
    HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    if [ -z "$HOST_IP" ]; then
        HOST_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "localhost")
    fi
else
    HOST_IP="localhost"
fi

PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

DEFAULT_PORT="${VITE_DEV_PORT:-${PORT:-5173}}"
FRONTEND_HOST="${VITE_DEV_HOST:-127.0.0.1}"
FRONTEND_PORT="$($PYTHON_BIN - <<'PY' "$DEFAULT_PORT" "$FRONTEND_HOST"
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

PORTS_FILE="$(cd "$(dirname "$0")" && pwd -P)/public/ports.json"
"$PYTHON_BIN" - <<'PY' "$PORTS_FILE" "$FRONTEND_PORT"
import json
import sys
from pathlib import Path

ports_file = Path(sys.argv[1])
frontend_port = sys.argv[2]
data = {}
if ports_file.exists():
    try:
        data = json.loads(ports_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
data["frontendPort"] = frontend_port
ports_file.parent.mkdir(parents=True, exist_ok=True)
ports_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY

echo "🚀 Starting Monkey Brain Segmentation Notebook server..."
echo ""
echo "════════════════════════════════════════════════════════════"
echo ""
echo "📋 Server Info:"
echo "  ├─ Local access:  http://localhost:$FRONTEND_PORT"
if [ "$FRONTEND_HOST" = "0.0.0.0" ] || [ "$FRONTEND_HOST" = "::" ]; then
echo "  ├─ Network access: http://$HOST_IP:$FRONTEND_PORT"
else
echo "  ├─ Network access: disabled by default"
fi
echo "  └─ Port: $FRONTEND_PORT"
echo ""
echo "📱 Main pages:"
echo "  ├─ 🏠 Home:           http://localhost:$FRONTEND_PORT/"
echo "  ├─ 🧠 Visualization:  http://localhost:$FRONTEND_PORT/visualization"
echo "  ├─ ⚙️  Config:         http://localhost:$FRONTEND_PORT/config"
echo "  ├─ 🤖 Assistant:      http://localhost:$FRONTEND_PORT/agent"
echo "  └─ 📊 Segmentation:   http://localhost:$FRONTEND_PORT/segmentation"
echo ""
echo "💡 Usage:"
echo "  • Run this script on a Linux server"
echo "  • Access via SSH port forwarding: ssh -L $FRONTEND_PORT:localhost:$FRONTEND_PORT user@server"
echo "  • For production, serve the built dist/ directory with Nginx"
echo ""
echo "⏹️  Press Ctrl+C to stop the server"
echo ""
echo "════════════════════════════════════════════════════════════"
echo ""

# Start dev server (port can be overridden via VITE_DEV_PORT or PORT)
export CHOKIDAR_USEPOLLING=true
export CHOKIDAR_INTERVAL=500
npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
