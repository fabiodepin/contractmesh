#!/usr/bin/env bash
# Export the generated ContractMesh workspace graph as JSON.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

exec python3 -m contractmesh.engine.export_workspace_graph "$WORKSPACE_DIR"
