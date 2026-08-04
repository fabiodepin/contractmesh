#!/usr/bin/env bash
# Phase 2 (PR5+): embedding vectors for hybrid search. Keyword search remains the default until this is implemented.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[INFO] embed-search-index: not implemented yet (roadmap PR5+)." >&2
echo "[INFO] Run: bash scripts/build-search-index.sh  # keyword index + MCP fetch_hits" >&2
echo "[INFO] Retrieval regression: bash scripts/test-mcp-workspace-knowledge.sh" >&2
echo "[INFO] Planned: per-chunk vectors, embedding.status=ready in manifest, hybrid re-rank in workspace_search.py" >&2
exit 0
