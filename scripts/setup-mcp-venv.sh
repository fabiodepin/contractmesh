#!/usr/bin/env bash
# Create scripts/.venv-mcp and install MCP dependencies (Python 3.10+).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv-mcp"

pick_python() {
  for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" >/dev/null 2>&1; then
      if "$cmd" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        echo "$cmd"
        return 0
      fi
    fi
  done
  return 1
}

PY="$(pick_python)" || {
  echo "[FAIL] Python 3.10+ required for MCP (package mcp)." >&2
  exit 1
}

echo "[ok] using $PY"
"$PY" -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install -q -r "$SCRIPT_DIR/requirements-mcp.txt"
echo "[ok] venv ready: $VENV_DIR"

bash "$SCRIPT_DIR/write-mcp-cursor-config.sh"
echo "Restart MCP in Cursor → Settings → MCP (workspace-knowledge)."
