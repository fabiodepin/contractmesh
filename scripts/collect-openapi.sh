#!/usr/bin/env bash
# Copy OpenAPI specs listed in docs/ai/openapi-sources.yaml into .contractmesh/generated/openapi/.
# Expects simple lines under specs: like "  repo-name: relative/path.json"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MAP="$WORKSPACE_DIR/docs/ai/openapi-sources.yaml"
DEST="$WORKSPACE_DIR/.contractmesh/generated/openapi"

if grep -qE '^specs:[[:space:]]*\{\}[[:space:]]*$' "$MAP" 2>/dev/null || ! grep -qE '^[[:space:]]+[a-zA-Z0-9-]+:[[:space:]]+[^#[:space:]]' "$MAP" 2>/dev/null; then
  echo "No OpenAPI paths configured in openapi-sources.yaml (specs empty). Nothing to collect."
  exit 0
fi

mkdir -p "$DEST"

while IFS= read -r line; do
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  if [[ "$line" =~ ^[[:space:]]+([a-zA-Z0-9-]+):[[:space:]]+([^[:space:]#]+) ]]; then
    repo="${BASH_REMATCH[1]}"
    rel="${BASH_REMATCH[2]}"
    src="$WORKSPACE_DIR/$repo/$rel"
    if [[ ! -f "$src" ]]; then
      echo "WARN: missing spec $src (repo $repo)" >&2
      continue
    fi
    base=$(basename "$rel")
    cp -f "$src" "$DEST/${repo}-${base}"
    echo "Collected $repo -> ${repo}-${base}"
  fi
done <"$MAP"

echo "Done. Output under $DEST"
