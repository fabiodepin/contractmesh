#!/usr/bin/env bash
# Build .contractmesh/index/search-index.manifest.json, search-index.local.json, and chunks/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

REPOS_CSV="$(python3 -m contractmesh.engine.workspace_manifest repos-csv "$WORKSPACE_DIR")"

exec python3 -m contractmesh.engine.build_search_index "$WORKSPACE_DIR" "$REPOS_CSV"
