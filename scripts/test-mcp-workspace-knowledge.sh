#!/usr/bin/env bash
# Smoke test: workspace knowledge MCP library (no stdio MCP).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE="${ROOT}/tests/fixtures/basic-workspace"
cd "$ROOT"
VENV="${ROOT}/scripts/.venv-mcp/bin/python"
if [[ ! -x "$VENV" ]]; then
  VENV=python3
fi
export CONTRACTMESH_WORKSPACE="$FIXTURE"
if [[ ! -f "${FIXTURE}/.contractmesh/index/search-index.manifest.json" ]]; then
  echo "[WARN] fixture index missing — run: contractmesh index (in fixture)" >&2
  exit 0
fi
echo "[ok] running test_fetch_hits + test_mcp_golden_queries"
(
  cd "${ROOT}/scripts/lib"
  "$VENV" -m unittest discover -s . -p 'test_fetch_hits.py' -v
  "$VENV" -m unittest discover -s . -p 'test_mcp_golden_queries.py' -v
)
echo "[ok] MCP workspace-knowledge smoke passed"
