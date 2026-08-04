#!/usr/bin/env python3
"""Smoke test: basic-workspace fixture indexes with docs, code and test anchors."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from contractmesh.paths import repo_root
ROOT = repo_root()
LIB = ROOT / "contractmesh" / "engine"
FIXTURE = ROOT / "tests" / "fixtures" / "basic-workspace"

if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from .test_fixture_support import ensure_basic_fixture_index, fixture_manifest_path  # noqa: E402
from contractmesh.engine.workspace_search import load_index  # noqa: E402


class TestBasicWorkspaceFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not FIXTURE.is_dir():
            raise unittest.SkipTest("basic-workspace fixture missing")
        cls.workspace = ensure_basic_fixture_index()

    def test_manifest_has_contract(self) -> None:
        manifest, _ = load_index(self.workspace)
        contracts = [
            d for d in manifest.get("documents", []) if d.get("external_id") == "APP-CONTRACT-001"
        ]
        self.assertTrue(contracts, "expected APP-CONTRACT-001 in index")

    def test_manifest_has_code_anchor(self) -> None:
        manifest, _ = load_index(self.workspace)
        anchors = [
            d
            for d in manifest.get("documents", [])
            if d.get("kind") == "code_anchor" and d.get("symbol") == "ExampleService"
        ]
        self.assertTrue(anchors, "expected ExampleService code anchor")

    def test_manifest_has_test_anchor(self) -> None:
        manifest, _ = load_index(self.workspace)
        anchors = [
            d
            for d in manifest.get("documents", [])
            if d.get("kind") == "test_anchor" and "test_example" in d.get("path", "")
        ]
        self.assertTrue(anchors, "expected test_example test anchor")

    def test_manifest_path_under_contractmesh(self) -> None:
        self.assertTrue(fixture_manifest_path().is_file())


if __name__ == "__main__":
    unittest.main()
