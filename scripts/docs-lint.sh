#!/usr/bin/env bash
#
# docs-lint v1: contractmesh.yml -> repositories.md, AGENTS.md
# headings and contracts/README.md status legend when repo directories exist.
#

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

require_all=0
case "${1:-}" in
  --require-all-repos) require_all=1 ;;
  --help|-h)
    printf '%s\n' \
      "Usage: docs-lint.sh [--require-all-repos]" \
      "  Validates workspace governance and per-repo docs when clones exist." \
      "  --require-all-repos: fail if a configured repo is not cloned."
    exit 0
    ;;
esac

REPOS=()
while IFS= read -r repo || [[ -n "$repo" ]]; do
  [[ -z "$repo" ]] && continue
  REPOS+=("$repo")
done < <(python3 -m contractmesh.engine.workspace_manifest repos-lines "$WORKSPACE_DIR")

fails=0
warns=0

bump_fail() { echo "[FAIL] $*"; fails=$((fails + 1)); }
bump_warn() { echo "[WARN] $*"; warns=$((warns + 1)); }
bump_skip() { echo "[SKIP] $*"; }

if ! python3 -m contractmesh.engine.validate_workspace_docs "$WORKSPACE_DIR"; then
  fails=$((fails + 1))
fi

in_repos() {
  local x="$1" r
  for r in "${REPOS[@]}"; do
    [[ "${r##*/}" == "$x" ]] && return 0
  done
  return 1
}

# --- repositories.md: every REPOS appears; reciprocity from Repository column only ---
repos_md="$WORKSPACE_DIR/docs/ai/repositories.md"
if [[ ! -f "$repos_md" ]]; then
  bump_fail "missing docs/ai/repositories.md"
else
  if ! grep -qE '^\|[[:space:]]*Repository[[:space:]]*\|' "$repos_md"; then
    bump_fail "docs/ai/repositories.md: no table header column 'Repository' (exact name required)"
  else
    table_repos=()
    after_sep=0
    while IFS= read -r line || [[ -n "$line" ]]; do
      if [[ "$line" =~ ^\|[[:space:]]*Repository[[:space:]]*\| ]]; then
        continue
      fi
      if [[ "$line" =~ ^\|[[:space:]]*-+.*\|[[:space:]]*-+ ]]; then
        after_sep=1
        continue
      fi
      if [[ "$after_sep" -eq 1 ]] && [[ "$line" == \|* ]]; then
        rest="${line#|}"
        first="${rest%%|*}"
        first="${first//\*\*/}"
        first="${first#"${first%%[![:space:]]*}"}"
        first="${first%"${first##*[![:space:]]}"}"
        [[ -z "$first" ]] && continue
        [[ "$first" == -* ]] && continue
        table_repos+=("$first")
      elif [[ "$after_sep" -eq 1 ]] && [[ "$line" != \|* ]]; then
        break
      fi
    done <"$repos_md"

    if [[ "${#table_repos[@]}" -gt 0 ]]; then
      for r in "${REPOS[@]}"; do
        repo_name="${r##*/}"
        found=0
        for t in "${table_repos[@]}"; do
          if [[ "$t" == "$repo_name" ]]; then
            found=1
            break
          fi
        done
        if [[ "$found" -eq 0 ]]; then
          bump_fail "repositories.md: REPOS entry '$repo_name' not found in Repository column table"
        fi
      done

      for t in "${table_repos[@]}"; do
        if ! in_repos "$t"; then
          bump_fail "repositories.md: table row Repository '$t' is not in REPOS"
        fi
      done
    fi
  fi
fi

# --- Per-repo: AGENTS.md + docs/ai/contracts/README.md ---
agents_required_patterns=(
  'AI Mapping Version'
  'Status'
  'Repository Role'
  'Responsibilities'
  'Non-Responsibilities'
  'Docs Index'
)

contracts_readme_patterns=(Stub 'To Validate' Partial '[Ss]tatus' '[Ll]egend' '[Tt]ouchpoints' '[Pp]olítica' '[Cc]ontracts')

for repo in "${REPOS[@]}"; do
  rp="$WORKSPACE_DIR/$repo"
  if [[ ! -d "$rp" ]]; then
    if [[ "$require_all" -eq 1 ]]; then
      bump_fail "repo directory missing (required): $repo"
    else
      bump_skip "$repo - directory missing (AGENTS/contracts checks skipped)"
    fi
    continue
  fi

  agents="$rp/AGENTS.md"
  if [[ -f "$agents" ]]; then
    for pat in "${agents_required_patterns[@]}"; do
      if ! grep -qiE "^#{1,6}[[:space:]]+.*${pat//\//\\/}" "$agents"; then
        bump_fail "$repo/AGENTS.md: missing expected heading section matching '$pat'"
      fi
    done
  else
    bump_fail "$repo/AGENTS.md missing"
  fi

  cr="$rp/docs/ai/contracts/README.md"
  if [[ -f "$cr" ]]; then
    ok=0
    for pat in "${contracts_readme_patterns[@]}"; do
      if grep -qiE "$pat" "$cr"; then
        ok=1
        break
      fi
    done
    if [[ "$ok" -eq 0 ]]; then
      bump_fail "$repo/docs/ai/contracts/README.md: expected status legend keywords (Stub / To Validate / Partial / status / legend)"
    fi
  else
    bump_skip "$repo/docs/ai/contracts/README.md not present (skip legend check)"
  fi
done

if [[ "$fails" -gt 0 ]]; then
  exit 1
fi
exit 0
