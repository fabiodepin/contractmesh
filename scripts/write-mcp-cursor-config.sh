#!/usr/bin/env bash
# Write .cursor/mcp.json with absolute paths (Cursor often spawns MCP with PWD=$HOME).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CURSOR_DIR="$WORKSPACE_DIR/.cursor"
MCP_JSON="$CURSOR_DIR/mcp.json"
VENV_PY="$SCRIPT_DIR/.venv-mcp/bin/python"
LAUNCHER="$SCRIPT_DIR/run-mcp-workspace-knowledge.sh"

if [ ! -x "$VENV_PY" ]; then
  echo "[FAIL] MCP venv missing. Run: bash scripts/setup-mcp-venv.sh" >&2
  exit 1
fi

chmod +x "$LAUNCHER" 2>/dev/null || true

mkdir -p "$CURSOR_DIR"

python3 - "$MCP_JSON" "$VENV_PY" "$WORKSPACE_DIR" <<'PY'
import json
import sys
from pathlib import Path

mcp_json, venv_py, workspace_dir = sys.argv[1:4]
payload = {
    "mcpServers": {
        "workspace-knowledge": {
            "command": venv_py,
            "args": ["-m", "contractmesh.mcp.server"],
            "env": {
                "CONTRACTMESH_WORKSPACE": workspace_dir,
                "WORKSPACE_ROOT": workspace_dir,
                "WORKSPACE_REPO": "contractmesh",
            },
            "cwd": workspace_dir,
        }
    }
}
path = Path(mcp_json)
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"[ok] wrote {path}")
PY

GLOBAL_MCP="${HOME}/.cursor/mcp.json"
mkdir -p "${HOME}/.cursor"
cp "$MCP_JSON" "$GLOBAL_MCP"
echo "[ok] synced global MCP config: $GLOBAL_MCP"
