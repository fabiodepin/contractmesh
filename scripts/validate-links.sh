#!/usr/bin/env bash
#
# Validate relative targets for Markdown inline links [text](path) in README.md and docs/**/*.md.
# Default: WARN for known repo not cloned; FAIL for missing targets. Use --strict to FAIL on not cloned.
#

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

strict=0
case "${1:-}" in
  --strict) strict=1 ;;
  --help|-h)
    printf '%s\n' \
      "Usage: validate-links.sh [--strict]" \
      "  Validates only inline links [text](path) in README.md and docs/**/*.md." \
      "  Default: [WARN] known repo not cloned; [FAIL] broken path." \
      "  --strict: not cloned becomes [FAIL]."
    exit 0
    ;;
esac

REPOS=()
while IFS= read -r repo || [[ -n "$repo" ]]; do
  [[ -z "$repo" ]] && continue
  REPOS+=("$repo")
done < <(python3 -m contractmesh.engine.workspace_manifest repos-lines "$WORKSPACE_DIR")
# shellcheck source=lib/workspace-md-links.sh
source "$SCRIPT_DIR/lib/workspace-md-links.sh"

fails=0

emit_for_link() {
  local md="$1" link="$2"
  local code="${WORKSPACE_MD_LINK_CODE:-}"
  local show=code
  case "$code" in
    OK|SKIP_EXTERNAL|SKIP_ANCHOR_ONLY) return 0 ;;
    WARN_REPO_NOT_CLONED)
      if [[ "$strict" -eq 1 ]]; then
        printf '[FAIL] %s -> %s (%s)\n' "$md" "$link" "${WORKSPACE_MD_LINK_MSG:-WARN_REPO_NOT_CLONED}"
        fails=$((fails + 1))
      else
        printf '[WARN] %s -> %s (%s)\n' "$md" "$link" "${WORKSPACE_MD_LINK_MSG:-repo not cloned}"
      fi
      ;;
    FAIL_TARGET_NOT_FOUND|FAIL_INVALID_ANCHOR)
      printf '[FAIL] %s -> %s (%s)\n' "$md" "$link" "${WORKSPACE_MD_LINK_MSG:-$code}"
      fails=$((fails + 1))
      ;;
    *)
      printf '[FAIL] %s -> %s (unknown code %s)\n' "$md" "$link" "${code:-?}"
      fails=$((fails + 1))
      ;;
  esac
}

scan_file() {
  local md="$1" docdir link
  docdir=$(dirname "$md")
  while IFS= read -r link || [[ -n "$link" ]]; do
    [[ -z "$link" ]] && continue
    workspace_md_classify_link "$WORKSPACE_DIR" "$md" "$docdir" "$link"
    emit_for_link "$md" "$link"
  done < <(workspace_md_extract_inline_link_targets "$md")
}

if [ -f "$WORKSPACE_DIR/README.md" ]; then
  scan_file "$WORKSPACE_DIR/README.md"
fi

if [ -d "$WORKSPACE_DIR/docs" ]; then
  while IFS= read -r -d '' md; do
    scan_file "$md"
  done < <(find "$WORKSPACE_DIR/docs" -name '*.md' -print0 2>/dev/null)
fi

if [[ "$fails" -gt 0 ]]; then
  exit 1
fi
exit 0
