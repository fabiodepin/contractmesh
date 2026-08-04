#!/usr/bin/env bash
# Maintainer-only: sync templates/basic/ → tests/fixtures/basic-workspace/
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rsync -a --delete "$ROOT/contractmesh/templates/basic/" "$ROOT/tests/fixtures/basic-workspace/"
echo "[ok] synced tests/fixtures/basic-workspace from templates/basic"
