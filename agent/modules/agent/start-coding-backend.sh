#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd -P)"
cd "$APP_DIR"
PYTHON="${AGENT_CODING_PYTHON:-$APP_DIR/.venv-coding/bin/python}"
export AGENT_ANALYSIS_DATA_ROOTS="${AGENT_ANALYSIS_DATA_ROOTS:-/data/xuancheng/datasets/structural_mri}"
export AGENT_DATA_ROOTS="${AGENT_DATA_ROOTS:-/data/xuancheng/datasets:/data/xuancheng/human:/data/xuancheng/human_fastsurfer:/data/xuancheng/T1WI_101:/data/xuancheng/t1_neurodiscovery:/data/xuancheng/featurize_20261011}"
export AGENT_DATA_DIRECTORY="${AGENT_DATA_DIRECTORY:-/data/xuancheng}"
export PRIMATEX_PIPELINE_IMAGE="${PRIMATEX_PIPELINE_IMAGE:-/data/xuancheng/agent/PrimateX_1_7.sif}"
export LANGSMITH_TRACING="${LANGSMITH_TRACING:-false}"
# Credentials use the existing PLATFORM_API_KEY/PRIMX_ACCESS_TOKEN configuration.
# This starts an independent listener and never rewrites the other service's ports.
exec "$PYTHON" -m uvicorn app:app --host "${AGENT_HOST:-127.0.0.1}" --port "${AGENT_PORT:-8110}"
