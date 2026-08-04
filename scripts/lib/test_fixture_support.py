#!/usr/bin/env python3
"""Shared helpers for tests against tests/fixtures/basic-workspace/."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from contractmesh.paths import repo_root
ROOT = repo_root()
LIB = ROOT / "contractmesh" / "engine"
FIXTURE = ROOT / "tests" / "fixtures" / "basic-workspace"
MANIFEST = FIXTURE / ".contractmesh" / "index" / "search-index.manifest.json"


def ensure_basic_fixture_git(fixture: Path | None = None) -> None:
    """Local git repo for git-aware tests (not committed to the tool repository)."""
    ws = fixture or FIXTURE
    if not shutil_which("git"):
        return
    git_dir = ws / ".git"
    if not git_dir.is_dir():
        subprocess.run(["git", "init"], cwd=ws, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@contractmesh.local"],
            cwd=ws,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "ContractMesh Test"],
            cwd=ws,
            check=True,
            capture_output=True,
        )
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True, capture_output=True)
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ws,
        capture_output=True,
        text=True,
        check=True,
    )
    if status.stdout.strip():
        subprocess.run(["git", "commit", "-m", "fixture snapshot"], cwd=ws, check=True, capture_output=True)
    count = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=ws,
        capture_output=True,
        text=True,
        check=True,
    )
    if int(count.stdout.strip() or "0") < 2:
        marker = ws / ".contractmesh" / "generated" / ".fixture-git-marker"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("git history marker for ContractMesh tests\n", encoding="utf-8")
        subprocess.run(["git", "add", str(marker.relative_to(ws))], cwd=ws, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "fixture second commit"], cwd=ws, check=True, capture_output=True)


def shutil_which(cmd: str) -> str | None:
    from shutil import which

    return which(cmd)


def ensure_basic_fixture_index() -> Path:
    if str(LIB) not in sys.path:
        sys.path.insert(0, str(LIB))
    ws = FIXTURE.resolve()
    os.environ["CONTRACTMESH_WORKSPACE"] = str(ws)
    ensure_basic_fixture_git(ws)
    if not MANIFEST.is_file():
        subprocess.run(
            [sys.executable, "-m", "contractmesh.engine.build_search_index", str(ws), "app=."],
            check=True,
            cwd=ROOT,
        )
    return ws


def fixture_manifest_path() -> Path:
    return MANIFEST
