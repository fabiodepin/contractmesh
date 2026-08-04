#!/usr/bin/env bash
#
# Doctor do workspace: requer Bash (arrays, source). Não POSIX sh.
#

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

REPOS=()
while IFS= read -r repo || [[ -n "$repo" ]]; do
  [[ -z "$repo" ]] && continue
  REPOS+=("$repo")
done < <(python3 -m contractmesh.engine.workspace_manifest repos-lines "$WORKSPACE_DIR")
# shellcheck source=lib/workspace-md-links.sh
source "$SCRIPT_DIR/lib/workspace-md-links.sh"

errors=0
warnings=0

bump_err() { echo "ERROR: $*"; errors=$((errors + 1)); }
bump_warn() { echo "WARN: $*"; warnings=$((warnings + 1)); }

workspace_doctor_apply_link_result() {
  local md="$1" link="$2"
  case "${WORKSPACE_MD_LINK_CODE:-}" in
    OK|SKIP_EXTERNAL|SKIP_ANCHOR_ONLY) ;;
    WARN_REPO_NOT_CLONED)
      bump_warn "link target missing (clone repo?): $md -> $link (${WORKSPACE_MD_LINK_MSG:-})"
      ;;
    FAIL_TARGET_NOT_FOUND|FAIL_INVALID_ANCHOR|"")
      bump_err "broken link in $md -> $link (${WORKSPACE_MD_LINK_MSG:-})"
      ;;
    *)
      bump_err "broken link in $md -> $link (code=${WORKSPACE_MD_LINK_CODE:-?})"
      ;;
  esac
}

workspace_doctor_scan_md_file() {
  local md="$1" docdir link
  docdir=$(dirname "$md")
  while IFS= read -r link || [[ -n "$link" ]]; do
    [[ -z "$link" ]] && continue
    workspace_md_classify_link "$WORKSPACE_DIR" "$md" "$docdir" "$link"
    workspace_doctor_apply_link_result "$md" "$link"
  done < <(workspace_md_extract_inline_link_targets "$md")
}

echo "========================================"
echo " ContractMesh - Check (doctor)"
echo " Mapping: $(python3 -m contractmesh.engine.workspace_manifest version "$WORKSPACE_DIR")"
echo "========================================"

if ! command -v git >/dev/null 2>&1; then
  bump_err "git not found in PATH"
else
  echo "[ok] git: $(command -v git)"
fi

if [ -n "${BASH_VERSION:-}" ]; then
  echo "[ok] bash: $BASH_VERSION"
else
  bump_warn "not running under bash"
fi

for base in status-all check-workspace check-toolchain list-repos validate-links docs-lint \
  setup-env gen-dependency-graph gen-workspace-health collect-openapi build-search-index search-workspace export-workspace-graph \
  sync-basic-fixture test-mcp-workspace-knowledge test-preflight-smoke setup-mcp-venv run-mcp-workspace-knowledge write-mcp-cursor-config embed-search-index; do
  p="$SCRIPT_DIR/${base}.sh"
  if [ ! -f "$p" ]; then
    bump_err "missing script: scripts/${base}.sh"
  elif [ ! -x "$p" ]; then
    bump_warn "not executable: scripts/${base}.sh (run: chmod +x \"$p\")"
  fi
done

required_docs_ai=(
  README.md
  repositories.md
  ecosystem-map.md
  glossary.md
  cross-repo-impact.md
  workspace-conventions.md
)

for f in "${required_docs_ai[@]}"; do
  rp="$WORKSPACE_DIR/docs/ai/$f"
  if [ ! -f "$rp" ]; then
    bump_err "missing required docs/ai file: docs/ai/$f"
  else
    echo "[ok] docs/ai/$f"
  fi
done

cd "$WORKSPACE_DIR"

for repo in "${REPOS[@]}"; do
  if [ ! -d "$repo" ]; then
    bump_warn "repo directory missing: $repo"
    continue
  fi

  if [ ! -d "$repo/.git" ]; then
    echo "[ok] local repo directory: $repo"
    continue
  fi

  if ! git -C "$repo" rev-parse '@{u}' >/dev/null 2>&1; then
    bump_warn "no upstream: $repo (branch $(git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?'))"
  else
    ab=$(git -C "$repo" rev-list --left-right --count '@{upstream}...HEAD' 2>/dev/null || true)
    if [ -n "$ab" ]; then
      behind=$(echo "$ab" | awk '{print $1}')
      ahead=$(echo "$ab" | awk '{print $2}')
      if [ "${behind:-0}" != "0" ] || [ "${ahead:-0}" != "0" ]; then
        bump_warn "divergente de upstream: $repo (behind=$behind ahead=$ahead)"
      fi
    fi
  fi

  if [ -n "$(git -C "$repo" status --porcelain 2>/dev/null)" ]; then
    bump_warn "dirty working tree: $repo"
  fi
done

if [ -f "$WORKSPACE_DIR/README.md" ]; then
  workspace_doctor_scan_md_file "$WORKSPACE_DIR/README.md"
fi

if [ -d "$WORKSPACE_DIR/docs" ]; then
  while IFS= read -r -d '' md; do
    workspace_doctor_scan_md_file "$md"
  done < <(find "$WORKSPACE_DIR/docs" -name '*.md' -print0 2>/dev/null)
fi

INDEX_MANIFEST="$WORKSPACE_DIR/.contractmesh/index/search-index.manifest.json"
if [ ! -f "$INDEX_MANIFEST" ]; then
  bump_warn "search index not built (run: contractmesh index)"
else
  echo "[ok] .contractmesh/index/search-index.manifest.json"
fi

MCP_VENV="$WORKSPACE_DIR/scripts/.venv-mcp/bin/python"
if [ ! -x "$MCP_VENV" ]; then
  echo "[skip] MCP venv not installed (optional; run: bash scripts/setup-mcp-venv.sh)"
else
  echo "[ok] scripts/.venv-mcp (workspace-knowledge MCP)"
fi

MCP_JSON="$WORKSPACE_DIR/.cursor/mcp.json"
if [ -f "$MCP_JSON" ]; then
  if grep -q "$WORKSPACE_DIR/contractmesh.mcp.server" "$MCP_JSON" 2>/dev/null; then
    echo "[ok] .cursor/mcp.json (workspace-knowledge, absolute paths)"
  else
    bump_warn "MCP config outdated (run: bash scripts/write-mcp-cursor-config.sh)"
  fi
else
  echo "[skip] .cursor/mcp.json not generated (optional; run: bash scripts/setup-mcp-venv.sh)"
fi

if [ -f "$INDEX_MANIFEST" ] && [ -x "$MCP_VENV" ]; then
  if ! WORKSPACE_ROOT="$WORKSPACE_DIR" bash "$WORKSPACE_DIR/scripts/test-mcp-workspace-knowledge.sh" >/dev/null 2>&1; then
    bump_warn "MCP retrieval/smoke tests failed (run: bash scripts/test-mcp-workspace-knowledge.sh)"
  else
    echo "[ok] MCP workspace-knowledge smoke tests"
  fi
fi

echo
echo "----------------------------------------"
echo " Summary: errors=$errors warnings=$warnings"
echo "========================================"

if [ "$errors" -gt 0 ]; then
  exit 1
fi
exit 0
