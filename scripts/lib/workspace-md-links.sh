# shellcheck shell=bash
# scripts/lib/workspace-md-links.sh — markdown link validation helpers.
# Not for direct execution.
#
# Returns: (workspace_md_classify_link sets WORKSPACE_MD_LINK_CODE / WORKSPACE_MD_LINK_MSG)
#   OK
#   WARN_REPO_NOT_CLONED
#   FAIL_TARGET_NOT_FOUND
#   FAIL_INVALID_ANCHOR   (reserved; v1 does not emit)
#   SKIP_EXTERNAL
#   SKIP_ANCHOR_ONLY
#
# v1: only file-path resolution; no anchor-within-file validation.

workspace_is_known_repo_dir() {
  local name="$1" r
  for r in "${REPOS[@]}"; do
    if [[ "$r" == "$name" ]]; then
      return 0
    fi
  done
  return 1
}

# Print one raw target per line: content of (...) from non-image [text](path) links.
# Fenced ``` / ~~~ code blocks are skipped so examples like [text](path) are not validated.
workspace_md_extract_inline_link_targets() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  awk '
  function process_line(line,    s, st, len, full, target) {
    s = line
    while (match(s, /\[[^]]+\]\([^)]+\)/)) {
      st = RSTART
      len = RLENGTH
      full = substr(s, st, len)
      if (st > 1 && substr(s, st - 1, 1) == "!") {
        s = substr(s, st + len)
        continue
      }
      if (match(full, /\(([^)]+)\)/)) {
        print substr(full, RSTART + 1, RLENGTH - 2)
      }
      s = substr(s, st + len)
    }
  }
  BEGIN { inblk = 0 }
  /^[[:space:]]*```/ || /^[[:space:]]*~~~/ {
    inblk = !inblk
    next
  }
  inblk { next }
  {
    line = $0
    while (match(line, /`[^`]*`/)) {
      line = substr(line, 1, RSTART - 1) " " substr(line, RSTART + RLENGTH)
    }
    process_line(line)
  }
  ' "$file"
}

# Args: WORKSPACE_ROOT MD_PATH DOCDIR LINK
workspace_md_classify_link() {
  local work_dir="$1" md_path="$2" docdir="$3" link="$4"
  local path_only frag tail head target

  WORKSPACE_MD_LINK_CODE=""
  WORKSPACE_MD_LINK_MSG=""

  case "$link" in
    http://*|https://*|mailto:*)
      WORKSPACE_MD_LINK_CODE=SKIP_EXTERNAL
      WORKSPACE_MD_LINK_MSG="external URL"
      return 0
      ;;
  esac

  path_only="${link%%#*}"
  if [[ -z "$path_only" ]]; then
    WORKSPACE_MD_LINK_CODE=SKIP_ANCHOR_ONLY
    WORKSPACE_MD_LINK_MSG="anchor-only"
    return 0
  fi
  link="$path_only"

  if [[ "$md_path" == "$work_dir/docs/ai/"* ]] && [[ "$link" == ../* ]]; then
    tail="${link#../}"
    target="$work_dir/$tail"
    if [ -e "$target" ]; then
      WORKSPACE_MD_LINK_CODE=OK
      WORKSPACE_MD_LINK_MSG="exists"
      return 0
    fi
    head="${tail%%/*}"
    if workspace_is_known_repo_dir "$head"; then
      WORKSPACE_MD_LINK_CODE=WARN_REPO_NOT_CLONED
      WORKSPACE_MD_LINK_MSG="known repo not cloned: $head (expected $target)"
      return 0
    fi
    WORKSPACE_MD_LINK_CODE=FAIL_TARGET_NOT_FOUND
    WORKSPACE_MD_LINK_MSG="broken link (expected $target)"
    return 0
  fi

  if ( cd "$docdir" && test -e "$link" ); then
    WORKSPACE_MD_LINK_CODE=OK
    WORKSPACE_MD_LINK_MSG="exists"
    return 0
  fi
  WORKSPACE_MD_LINK_CODE=FAIL_TARGET_NOT_FOUND
  WORKSPACE_MD_LINK_MSG="broken relative link from $docdir"
  return 0
}
