#!/usr/bin/env bash
# Generate .contractmesh/generated/dependency-graph.mmd and dependency-graph.json from
# docs/ai/dependency-graph.source.yaml (curated list).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC="$WORKSPACE_DIR/docs/ai/dependency-graph.source.yaml"
OUT_DIR="$WORKSPACE_DIR/.contractmesh/generated"
OUT_MMD="$OUT_DIR/dependency-graph.mmd"
OUT_JSON="$OUT_DIR/dependency-graph.json"

mkdir -p "$OUT_DIR"

if [[ ! -f "$SRC" ]]; then
  echo "ERROR: missing $SRC" >&2
  exit 1
fi

pairs=()
cur_from=
while IFS= read -r line || [[ -n "$line" ]]; do
  if [[ "$line" =~ from:[[:space:]]*([a-zA-Z0-9-]+) ]]; then
    cur_from="${BASH_REMATCH[1]}"
  elif [[ "$line" =~ to:[[:space:]]*([a-zA-Z0-9-]+) ]]; then
    to="${BASH_REMATCH[1]}"
    if [[ -n "$cur_from" ]]; then
      pairs+=("${cur_from}|${to}")
    fi
    cur_from=
  fi
done <"$SRC"

{
  echo "graph TD"
  for p in "${pairs[@]}"; do
    from="${p%%|*}"
    to="${p#*|}"
    printf '  "%s" --> "%s"\n' "$from" "$to"
  done
} >"$OUT_MMD"

json_edges=()
for p in "${pairs[@]}"; do
  from="${p%%|*}"
  to="${p#*|}"
  json_edges+=("{\"from\":\"$from\",\"to\":\"$to\"}")
done

{
  printf '{"version":1,"edges":['
  first=1
  for je in "${json_edges[@]}"; do
    if [[ "$first" -eq 1 ]]; then
      first=0
    else
      printf ','
    fi
    printf '%s' "$je"
  done
  printf ']}\n'
} >"$OUT_JSON"

echo "Wrote $OUT_MMD and $OUT_JSON (${#pairs[@]} edges)."
