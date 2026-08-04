#!/usr/bin/env python3
"""Tests for workspace path resolution."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import sys

from contractmesh.paths import repo_root
ROOT = repo_root()
LIB = ROOT / "contractmesh" / "engine"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from contractmesh.engine.workspace_paths import (  # noqa: E402
    WORKSPACE_NOT_FOUND_MSG,
    find_workspace,
    require_workspace,
    workspace_layout,
)

FIXTURE = ROOT / "tests" / "fixtures" / "basic-workspace"


class TestWorkspacePaths(unittest.TestCase):
    def test_fixture_layout_paths(self) -> None:
        layout = workspace_layout(FIXTURE)
        self.assertEqual(layout.manifest_path.name, "search-index.manifest.json")
        self.assertIn(".contractmesh/index", str(layout.index_dir))

    def test_find_workspace_from_env(self) -> None:
        old = os.environ.get("CONTRACTMESH_WORKSPACE")
        os.environ["CONTRACTMESH_WORKSPACE"] = str(FIXTURE.resolve())
        try:
            self.assertEqual(find_workspace(), FIXTURE.resolve())
        finally:
            if old is None:
                os.environ.pop("CONTRACTMESH_WORKSPACE", None)
            else:
                os.environ["CONTRACTMESH_WORKSPACE"] = old

    def test_require_workspace_fails_without_marker(self) -> None:
        old_ws = os.environ.pop("CONTRACTMESH_WORKSPACE", None)
        old_root = os.environ.pop("WORKSPACE_ROOT", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(FileNotFoundError) as ctx:
                    require_workspace(Path(tmp))
                self.assertIn("contractmesh init --here", str(ctx.exception))
        finally:
            if old_ws is not None:
                os.environ["CONTRACTMESH_WORKSPACE"] = old_ws
            if old_root is not None:
                os.environ["WORKSPACE_ROOT"] = old_root


if __name__ == "__main__":
    unittest.main()
