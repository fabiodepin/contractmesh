#!/usr/bin/env python3
"""Structural graph tests (skipped when flag off in basic fixture)."""

import sys
import unittest
from pathlib import Path


from .test_fixture_support import ensure_basic_fixture_index, fixture_manifest_path  # noqa: E402
from contractmesh.engine.workspace_search import load_index, orient_workspace  # noqa: E402


class TestStructuralGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace = ensure_basic_fixture_index()
        if not fixture_manifest_path().is_file():
            raise unittest.SkipTest("index missing")
        cls.manifest, _ = load_index(cls.workspace)

    def test_manifest_structural_edges_when_enabled(self) -> None:
        edges = self.manifest.get("structural_edges") or []
        if not edges:
            self.skipTest("structural_graph flag off")
        self.assertTrue(len(edges) > 0)

    def test_orient_workspace(self) -> None:
        result = orient_workspace(self.workspace, self.manifest, repo=["app"])
        self.assertIn("top_contracts", result)


if __name__ == "__main__":
    unittest.main()
