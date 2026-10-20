#!/usr/bin/env bash
# Copyright (C) 2026 Wang Zheng Lab, Peking University
#
# This file is part of PrimateX.
#
# PrimateX is free software: you can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# PrimateX is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# If you use PrimateX in academic work, please cite:
# Xiaohui Yao*, Yichun Huang*, Kailong Cui*, ..., Shan Cong#, Zheng Wang#.
# Multi-agentic routing with PrimateX: standardized structural MRI analysis
# for non-human primates and humans.
#
# * Equal contribution.
# Correspondence (#): Shan Cong (shan.cong@hrbeu.edu.cn), Zheng Wang
# (zheng.wang@pku.edu.cn).
#
# See CITATION.cff for full citation details.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
cd "$SCRIPT_DIR"

PORT="${AGENT_PORT:-8100}"
HOST="${AGENT_HOST:-127.0.0.1}"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
else
  PYTHON_BIN=python
fi

SELECTED_PORT="$($PYTHON_BIN - <<'PY' "$PORT" "$HOST"
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

export AGENT_PORT="$SELECTED_PORT"
export AGENT_HOST="$HOST"
echo "[agent-backend] listening on ${AGENT_HOST}:${AGENT_PORT}"

PORTS_FILE="$(cd "$SCRIPT_DIR/../gui/monkey-brain-frontend" && pwd -P)/public/ports.json"
"$PYTHON_BIN" - <<'PY' "$PORTS_FILE" "$AGENT_PORT"
import json
import sys
from pathlib import Path

ports_file = Path(sys.argv[1])
agent_port = sys.argv[2]
data = {}
if ports_file.exists():
    try:
        data = json.loads(ports_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
data["agentPort"] = agent_port
ports_file.parent.mkdir(parents=True, exist_ok=True)
ports_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY

"$PYTHON_BIN" -m uvicorn app:app --host "$AGENT_HOST" --port "$AGENT_PORT"
