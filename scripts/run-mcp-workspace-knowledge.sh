#!/usr/bin/env bash
# Launcher for Cursor MCP (stdio). Requires: bash scripts/setup-mcp-venv.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PY="$SCRIPT_DIR/.venv-mcp/bin/python"

if [ ! -x "$VENV_PY" ]; then
  echo "[FAIL] MCP venv missing. Run: bash scripts/setup-mcp-venv.sh" >&2
  exit 1
fi

export CONTRACTMESH_WORKSPACE="${CONTRACTMESH_WORKSPACE:-$WORKSPACE_DIR}"
exec "$VENV_PY" -m contractmesh.mcp.server
