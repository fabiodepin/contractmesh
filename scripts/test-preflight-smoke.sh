#!/usr/bin/env bash
# Release smoke: preflight_change card for basic-workspace fixture symbol.
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
"$VENV" - <<'PY'
import json
import os
from pathlib import Path

from contractmesh.engine.preflight_change import preflight_change
from contractmesh.engine.workspace_search import load_index

workspace = Path(os.environ["CONTRACTMESH_WORKSPACE"]).resolve()
manifest, local = load_index(workspace)
result, err = preflight_change(
    workspace,
    manifest,
    local,
    symbol="ExampleService.greet",
    repo=["app"],
)
if err:
    raise SystemExit(f"[FAIL] preflight_change: {err}")

card = result.get("card") or {}
policy = result.get("agent_policy") or {}
details = result.get("details") or {}

required_card = ("risk", "why", "review", "run", "text")
for key in required_card:
    if key not in card:
        raise SystemExit(f"[FAIL] card missing {key}: {json.dumps(result, indent=2)}")

if card["risk"] not in {"LOW", "MEDIUM", "HIGH"}:
    raise SystemExit(f"[FAIL] invalid risk: {card['risk']}")

review = card.get("review") or []
if not review:
    raise SystemExit("[FAIL] expected at least one review label (contract or gap)")

if card["risk"] == "HIGH" and not policy.get("requires_confirmation"):
    raise SystemExit("[FAIL] HIGH risk must set agent_policy.requires_confirmation")

if "details" not in result or "contracts" not in details:
    raise SystemExit("[FAIL] details payload missing contract evidence")

print("[ok] preflight_change smoke")
print(card["text"])
PY
