#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

case "${1:-}" in
  --version|-V)
    python3 -m contractmesh.engine.workspace_manifest version "$WORKSPACE_DIR"
    exit 0
    ;;
  --help|-h)
    printf '%s\n' "Usage: list-repos.sh [--version|-V|--help|-h]" "Prints one repository path per line from contractmesh.yml."
    exit 0
    ;;
esac

python3 -m contractmesh.engine.workspace_manifest repos-lines "$WORKSPACE_DIR"
