#!/usr/bin/env bash
#
# Repository status across REPOS (table by default; --blocks for legacy output).
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

REPOS=()
while IFS= read -r repo || [[ -n "$repo" ]]; do
  [[ -z "$repo" ]] && continue
  REPOS+=("$repo")
done < <(python3 -m contractmesh.engine.workspace_manifest repos-lines "$WORKSPACE_DIR")

format=table
verbose=0
wide_remote=0

usage() {
  cat <<'EOF'
Usage: status-all.sh [--blocks] [--verbose] [--wide] [--help]

  Default: aligned table (repo, branch, status, ahead, behind, remote).
  --blocks   Legacy block output per repository.
  --verbose  After the table, list git status --short for repos with changes.
  --wide     Show full origin URL in the remote column (table mode).
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --blocks) format=blocks; shift ;;
    --verbose) verbose=1; shift ;;
    --wide) wide_remote=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

cd "$WORKSPACE_DIR"

status_short_remote() {
  local url="$1"
  case "$url" in
    git@*:*/*)
      local path="${url#*:}"
      path="${path%/}"
      path="${path%.git}"
      echo "$path"
      ;;
    https://* | http://*)
      local path="${url#*://}"
      path="${path#*/}"
      path="${path%/}"
      path="${path%.git}"
      echo "$path"
      ;;
    no-origin) echo "-" ;;
    *) echo "$url" ;;
  esac
}

status_collect() {
  local repo="$1"
  _s_repo="$repo"
  _s_branch="-"
  _s_status="NO GIT"
  _s_ahead="-"
  _s_behind="-"
  _s_remote="-"
  _s_remote_full="-"
  _s_porcelain=""

  if [ ! -d "$repo" ]; then
    _s_status="MISSING"
    return 0
  fi

  if [ ! -d "$repo/.git" ]; then
    _s_status="LOCAL"
    return 0
  fi

  _s_branch=$(git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
  _s_remote_full=$(git -C "$repo" remote get-url origin 2>/dev/null || echo "no-origin")
  if [ "$wide_remote" -eq 1 ]; then
    _s_remote="$_s_remote_full"
  else
    _s_remote=$(status_short_remote "$_s_remote_full")
  fi

  _s_porcelain=$(git -C "$repo" status --short 2>/dev/null || true)
  if [ -z "$_s_porcelain" ]; then
    _s_status="CLEAN"
  else
    local n
    n=$(printf '%s\n' "$_s_porcelain" | sed '/^$/d' | wc -l | tr -d ' ')
    _s_status="CHANGES ($n)"
  fi

  local ahead_behind
  ahead_behind=$(git -C "$repo" rev-list --left-right --count '@{upstream}...HEAD' 2>/dev/null || true)
  if [ -n "$ahead_behind" ]; then
    _s_behind=$(echo "$ahead_behind" | awk '{print $1}')
    _s_ahead=$(echo "$ahead_behind" | awk '{print $2}')
  fi
}

status_print_blocks() {
  local repo="$1"
  echo
  echo "[$repo]"
  if [ "$_s_status" = "MISSING" ] || [ "$_s_status" = "LOCAL" ]; then
    echo "  $_s_status"
    return 0
  fi
  echo "  Branch : $_s_branch"
  echo "  Remote : $_s_remote_full"
  if [ "$_s_status" = "CLEAN" ]; then
    echo "  Status : CLEAN"
  else
    echo "  Status : CHANGES"
    printf '%s\n' "$_s_porcelain" | sed '/^$/d' | sed 's/^/    /'
  fi
  if [ "$_s_ahead" != "-" ]; then
    echo "  Ahead  : $_s_ahead"
    echo "  Behind : $_s_behind"
  fi
}

status_max_len() {
  local max=0 len
  for len in "$@"; do
    [ "${#len}" -gt "$max" ] && max=${#len}
  done
  echo "$max"
}

status_print_table() {
  local repos=() branches=() statuses=() aheads=() behinds=() remotes=()
  local porcelains=()
  local repo

  for repo in "${REPOS[@]}"; do
    status_collect "$repo"
    repos+=("$_s_repo")
    branches+=("$_s_branch")
    statuses+=("$_s_status")
    aheads+=("$_s_ahead")
    behinds+=("$_s_behind")
    remotes+=("$_s_remote")
    porcelains+=("$_s_porcelain")
  done

  local w_repo w_branch w_status w_ahead w_behind w_remote
  w_repo=$(status_max_len "REPO" "${repos[@]}")
  w_branch=$(status_max_len "BRANCH" "${branches[@]}")
  w_status=$(status_max_len "STATUS" "${statuses[@]}")
  w_ahead=$(status_max_len "AHEAD" "${aheads[@]}")
  w_behind=$(status_max_len "BEHIND" "${behinds[@]}")
  w_remote=$(status_max_len "REMOTE" "${remotes[@]}")

  [ "$w_repo" -lt 4 ] && w_repo=4
  [ "$w_branch" -lt 6 ] && w_branch=6
  [ "$w_status" -lt 6 ] && w_status=6
  [ "$w_ahead" -lt 5 ] && w_ahead=5
  [ "$w_behind" -lt 6 ] && w_behind=6
  [ "$w_remote" -lt 6 ] && w_remote=6

  local sep
  sep=$(printf '%*s' "$((w_repo + w_branch + w_status + w_ahead + w_behind + w_remote + 5))" '' | tr ' ' '-')

  printf "%-${w_repo}s  %-${w_branch}s  %-${w_status}s  %${w_ahead}s  %${w_behind}s  %-${w_remote}s\n" \
    "REPO" "BRANCH" "STATUS" "AHEAD" "BEHIND" "REMOTE"
  printf '%s\n' "$sep"

  local i
  for i in "${!repos[@]}"; do
    printf "%-${w_repo}s  %-${w_branch}s  %-${w_status}s  %${w_ahead}s  %${w_behind}s  %-${w_remote}s\n" \
      "${repos[$i]}" "${branches[$i]}" "${statuses[$i]}" "${aheads[$i]}" "${behinds[$i]}" "${remotes[$i]}"
  done

  if [ "$verbose" -eq 1 ]; then
    local has_changes=0
    for i in "${!repos[@]}"; do
      [ -z "${porcelains[$i]}" ] && continue
      has_changes=1
      echo
      echo "[${repos[$i]}] changes:"
      printf '%s\n' "${porcelains[$i]}" | sed '/^$/d' | sed 's/^/  /'
    done
    [ "$has_changes" -eq 0 ] && echo && echo "(no local changes in cloned repos)"
  fi
}

echo "========================================"
echo " ContractMesh - Repository Status"
echo "========================================"

if [ "$format" = "blocks" ]; then
  for repo in "${REPOS[@]}"; do
    status_collect "$repo"
    status_print_blocks "$repo"
  done
else
  echo
  status_print_table
fi

echo
echo "========================================"
echo " Done"
echo "========================================"
