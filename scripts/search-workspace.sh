#!/usr/bin/env bash
# Keyword search over .contractmesh/index/search-index.manifest.json (local RAG index).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

exec python3 -m contractmesh.engine.search_workspace "$@"
