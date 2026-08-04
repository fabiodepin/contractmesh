#!/usr/bin/env bash
# Prepare the local ContractMesh workspace.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$WORKSPACE_DIR"

echo "========================================"
echo " ContractMesh - Setup"
echo "========================================"

bash scripts/check-toolchain.sh
bash scripts/docs-lint.sh --require-all-repos
bash scripts/validate-links.sh
bash scripts/build-search-index.sh

echo
echo "[ok] workspace ready"
echo
echo "Try:"
echo "  contractmesh index"
echo "  contractmesh status"
echo "  bash scripts/test-mcp-workspace-knowledge.sh"
