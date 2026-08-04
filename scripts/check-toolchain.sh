#!/usr/bin/env bash
# Validate the minimal toolchain required for ContractMesh.

set -euo pipefail

warns=0
fails=0

b_warn() { printf '[WARN] %s\n' "$*"; warns=$((warns + 1)); }
b_fail() { printf '[FAIL] %s\n' "$*"; fails=$((fails + 1)); }
b_ok()   { printf '[OK] %s\n' "$*"; }

if [ -n "${BASH_VERSION:-}" ]; then
  b_ok "bash $BASH_VERSION"
else
  b_fail "bash not detected"
fi

if command -v git >/dev/null 2>&1; then
  b_ok "git $(git --version | sed 's/git version //')"
else
  b_fail "git not found"
fi

python_cmd=""
if command -v python3 >/dev/null 2>&1; then
  python_cmd="python3"
elif command -v python >/dev/null 2>&1; then
  python_cmd="python"
fi

if [ -n "$python_cmd" ]; then
  py_version="$($python_cmd - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
PY
)"
  py_major_minor="$($python_cmd - <<'PY'
import sys
print((sys.version_info.major, sys.version_info.minor) >= (3, 10))
PY
)"
  if [ "$py_major_minor" = "True" ]; then
    b_ok "$python_cmd $py_version"
  else
    b_fail "$python_cmd $py_version found; Python 3.10+ required"
  fi
else
  b_fail "python3 not found"
fi

if command -v node >/dev/null 2>&1; then
  b_ok "node $(node -v) (optional)"
else
  b_warn "node not found (optional; useful for TypeScript code anchors)"
fi

if command -v java >/dev/null 2>&1; then
  b_ok "java present (optional)"
else
  b_warn "java not found (optional; Java sources are still indexed as text when present)"
fi

echo "----------------------------------------"
if [ "$fails" -gt 0 ]; then
  printf 'Summary: FAIL=%s WARN=%s\n' "$fails" "$warns"
  exit 1
fi
printf 'Summary: OK (WARN=%s)\n' "$warns"
exit 0
