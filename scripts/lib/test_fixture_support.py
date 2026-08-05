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
    """Create deterministic local Git history for Git-aware tests."""
    ws = fixture or FIXTURE

    if not shutil_which("git"):
        return

    git_dir = ws / ".git"

    if not git_dir.is_dir():
        subprocess.run(
            ["git", "init"],
            cwd=ws,
            check=True,
            capture_output=True,
            text=True,
        )

    # Do not depend on the developer or CI runner's global Git configuration.
    subprocess.run(
        ["git", "config", "user.email", "test@contractmesh.local"],
        cwd=ws,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "ContractMesh Test"],
        cwd=ws,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=ws,
        check=True,
        capture_output=True,
        text=True,
    )

    subprocess.run(
        ["git", "add", "-A"],
        cwd=ws,
        check=True,
        capture_output=True,
        text=True,
    )

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ws,
        check=True,
        capture_output=True,
        text=True,
    )

    if status.stdout.strip():
        subprocess.run(
            ["git", "commit", "-m", "fixture snapshot"],
            cwd=ws,
            check=True,
            capture_output=True,
            text=True,
        )

    count_result = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=ws,
        capture_output=True,
        text=True,
    )

    commit_count = (
        int(count_result.stdout.strip())
        if count_result.returncode == 0 and count_result.stdout.strip()
        else 0
    )

    if commit_count < 2:
        subprocess.run(
            [
                "git",
                "commit",
                "--allow-empty",
                "-m",
                "fixture second commit",
            ],
            cwd=ws,
            check=True,
            capture_output=True,
            text=True,
        )


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
            [
                sys.executable,
                "-m",
                "contractmesh.engine.build_search_index",
                str(ws),
                "app=.",
            ],
            check=True,
            cwd=ROOT,
        )

    return ws


def fixture_manifest_path() -> Path:
    return MANIFEST
