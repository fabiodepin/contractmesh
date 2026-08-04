#!/usr/bin/env python3
"""Tests for git-aware MCP tools."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


from contractmesh.engine.git_workspace_tools import (  # noqa: E402
    _collect_docs_possibly_stale,
    _linked_docs_for_code_changes,
    _paths_match,
    _symbol_from_filename,
    branch_context,
    docs_drift_check,
    documentation_impact,
    pr_impact,
    suggest_tests_for_diff,
)
from .test_fixture_support import ensure_basic_fixture_index, fixture_manifest_path  # noqa: E402
from contractmesh.engine.workspace_search import load_index  # noqa: E402

PR_IMPACT_KEYS = {
    "changed_files",
    "contracts",
    "adrs",
    "code_anchors",
    "test_anchors",
    "known_gaps",
    "suggested_test_commands",
    "docs_possibly_stale",
    "documentation_impact",
    "provenance",
}


class TestGitHelpers(unittest.TestCase):
    def test_paths_match(self) -> None:
        self.assertTrue(_paths_match("example-app/src/Foo.java", "example-app/src/Foo.java"))
        self.assertTrue(_paths_match("src/Foo.java", "example-app/src/Foo.java"))

    def test_symbol_from_filename(self) -> None:
        self.assertEqual(_symbol_from_filename("src/ExampleService.py"), "ExampleService")
        self.assertEqual(
            _symbol_from_filename("tests/TestExampleService.py"),
            "TestExampleService",
        )


class TestGitWorkspaceToolsIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace = ensure_basic_fixture_index()
        manifest_path = fixture_manifest_path()
        if not manifest_path.is_file():
            raise unittest.SkipTest("search index missing")
        cls.manifest, cls.local = load_index(cls.workspace)
        try:
            subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=cls.workspace,
                capture_output=True,
                check=True,
            )
            cls.has_git = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            cls.has_git = False

    def test_linked_docs_for_example_service(self) -> None:
        changed = ["src/example.py"]
        linked = _linked_docs_for_code_changes(changed, self.manifest)
        paths = [c["path"] for c in linked["contracts"]]
        self.assertTrue(any("example-contract" in p for p in paths))
        self.assertTrue(linked["code_anchors"])

    def test_pr_impact_shape(self) -> None:
        changed = ["src/example.py"]
        with patch("contractmesh.engine.git_workspace_tools._collect_changed_paths", return_value=(changed, {"git_available": True})):
            result, err = pr_impact(self.workspace, self.manifest, self.local, base="main", head="HEAD")
        self.assertIsNone(err)
        self.assertTrue(PR_IMPACT_KEYS.issubset(result.keys()))
        self.assertIsInstance(result["test_anchors"], list)
        self.assertIsInstance(result["docs_possibly_stale"], list)
        self.assertIn("sources_consulted", result["provenance"])

    def setUp(self) -> None:
        if not self.has_git:
            self.skipTest("git not available")

    def test_pr_impact_against_head(self) -> None:
        result, err = pr_impact(
            self.workspace,
            self.manifest,
            self.local,
            base="HEAD~1",
            head="HEAD",
        )
        self.assertIsNone(err)
        self.assertIn("changed_files", result)
        self.assertIn("test_anchors", result)
        self.assertIn("provenance", result)

    def test_branch_context(self) -> None:
        result, err = branch_context(self.workspace, self.manifest, self.local)
        self.assertIsNone(err)
        self.assertIn("branch", result)
        self.assertIn("all_changed_files", result)

    def test_suggest_tests_for_diff_worktree(self) -> None:
        result, err = suggest_tests_for_diff(
            self.workspace,
            self.manifest,
            self.local,
            include_worktree=True,
        )
        self.assertIsNone(err)
        self.assertIn("related_tests", result)
        self.assertIn("suggested_test_commands", result)

    def test_docs_drift_check_detects_stale_contract(self) -> None:
        changed = ["src/example.py"]
        with patch("contractmesh.engine.git_workspace_tools._collect_changed_paths", return_value=(changed, {"git_available": True})):
            result, err = docs_drift_check(self.workspace, self.manifest)
        self.assertIsNone(err)
        self.assertTrue(result.get("deprecated"))
        self.assertEqual(result.get("replacement"), "documentation_impact")
        self.assertIn("documentation_impact", result)
        self.assertGreaterEqual(result["alert_count"], 0)

    def test_pr_impact_includes_documentation_impact(self) -> None:
        changed = ["src/example.py"]
        with patch(
            "contractmesh.engine.git_workspace_tools._collect_changed_paths",
            return_value=(changed, {"git_available": True}),
        ):
            result, err = pr_impact(self.workspace, self.manifest, self.local)
        self.assertIsNone(err)
        self.assertIn("documentation_impact", result)
        self.assertIn(result["documentation_impact"]["state"], ("none", "possible", "confirmed"))

    def test_documentation_impact_wrapper(self) -> None:
        result, err = documentation_impact(
            self.workspace,
            self.manifest,
            changed_paths=["src/example.py"],
        )
        self.assertIsNone(err)
        self.assertIn(result["state"], ("none", "possible", "confirmed"))
        self.assertIn("enforcement", result)

    def test_collect_docs_possibly_stale(self) -> None:
        changed = ["src/example.py"]
        stale = _collect_docs_possibly_stale(changed, self.manifest)
        self.assertIsInstance(stale, list)


if __name__ == "__main__":
    unittest.main()
