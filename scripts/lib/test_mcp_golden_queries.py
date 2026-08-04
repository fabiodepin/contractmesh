#!/usr/bin/env python3
"""Retrieval regression queries against the basic-workspace fixture."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


from contractmesh.engine.export_workspace_graph import export_graph  # noqa: E402
from .test_fixture_support import ensure_basic_fixture_index, fixture_manifest_path  # noqa: E402
from contractmesh.engine.workspace_search import (  # noqa: E402
    fetch_hits,
    impact_analysis,
    list_drift,
    load_index,
    orient_workspace,
    related_tests,
    search_documents,
)

GOLDEN_SEARCH = [
    {
        "name": "example_contract",
        "query": "example application contract",
        "kind": ["contract"],
        "repo": ["app"],
        "expect_path_contains": "docs/contracts/example-contract.md",
    },
    {
        "name": "gap_app_kg",
        "gap": "APP-KG-001",
        "expect_any_path_contains": ["known-gaps", "example-contract"],
    },
    {
        "name": "symbol_example_service",
        "symbol": "ExampleService",
        "kind": ["code_anchor"],
        "repo": ["app"],
        "expect_path_contains": "src/example.py",
    },
]

GOLDEN_FETCH = [
    {
        "name": "fetch_example_contract",
        "query": "ExampleService greeting",
        "kind": ["contract"],
        "repo": ["app"],
        "expect_path_contains": "docs/contracts/example-contract.md",
    },
    {
        "name": "fetch_gap",
        "gap": "APP-KG-001",
        "expect_any_path_contains": ["known-gaps", "example-contract"],
    },
]


class TestRetrievalRegressionQueries(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace = ensure_basic_fixture_index()
        if not fixture_manifest_path().is_file():
            raise unittest.SkipTest("basic fixture index missing")
        cls.manifest, cls.local = load_index(cls.workspace)

    def _top_path_search(self, case: dict) -> str:
        hits, err = search_documents(
            self.workspace,
            self.manifest,
            self.local,
            query=case.get("query", ""),
            gap=case.get("gap"),
            symbol=case.get("symbol"),
            kind=case.get("kind"),
            repo=case.get("repo"),
            limit=1,
        )
        self.assertIsNone(err, case["name"])
        self.assertGreaterEqual(len(hits), 1, case["name"])
        return hits[0].path

    def _top_path_fetch(self, case: dict) -> str:
        result, err = fetch_hits(
            self.workspace,
            self.manifest,
            self.local,
            query=case.get("query", ""),
            gap=case.get("gap"),
            symbol=case.get("symbol"),
            kind=case.get("kind"),
            repo=case.get("repo"),
            limit=1,
        )
        self.assertIsNone(err, case["name"])
        self.assertGreaterEqual(result["count"], 1, case["name"])
        hit = result["hits"][0]
        self.assertIn("chunk", hit, case["name"])
        return hit["path"]

    def test_golden_search(self) -> None:
        for case in GOLDEN_SEARCH:
            with self.subTest(case=case["name"]):
                path = self._top_path_search(case)
                if case.get("expect_any_path_contains"):
                    self.assertTrue(
                        any(part in path for part in case["expect_any_path_contains"]),
                        path,
                    )
                else:
                    self.assertIn(case["expect_path_contains"], path)

    def test_golden_fetch_hits(self) -> None:
        for case in GOLDEN_FETCH:
            with self.subTest(case=case["name"]):
                path = self._top_path_fetch(case)
                if case.get("expect_any_path_contains"):
                    self.assertTrue(
                        any(part in path for part in case["expect_any_path_contains"]),
                        path,
                    )
                else:
                    self.assertIn(case["expect_path_contains"], path)

    def test_golden_change_impact_graph(self) -> None:
        result, err = impact_analysis(
            self.workspace,
            self.manifest,
            self.local,
            query="What changes if ExampleService greeting rules change?",
            limit=8,
        )
        self.assertIsNone(err)
        self.assertGreaterEqual(len(result["contracts"]), 1)
        self.assertGreaterEqual(len(result["code_anchors"]), 1)
        self.assertTrue(result["provenance"]["sources_consulted"])

    def test_golden_related_tests_example_service(self) -> None:
        result, err = related_tests(
            self.workspace,
            self.manifest,
            self.local,
            symbol="ExampleService",
            repo=["app"],
        )
        self.assertIsNone(err)
        paths = [t["path"] for t in result["related_tests"]]
        self.assertTrue(any("test_example" in p for p in paths))

    def test_golden_orient_workspace(self) -> None:
        result = orient_workspace(self.workspace, self.manifest, repo=["app"])
        self.assertIn("top_contracts", result)

    def test_golden_list_drift_when_enabled(self) -> None:
        result = list_drift(self.manifest)
        flags = (self.manifest.get("build_stats") or {}).get("index_flags") or {}
        if not flags.get("drift"):
            self.skipTest("drift flag off")
        self.assertIn("findings", result)

    def test_workspace_graph_export_contains_example_contract(self) -> None:
        graph = export_graph(self.workspace)
        node_ids = {n["id"] for n in graph["nodes"]}
        self.assertIn("APP-CONTRACT-001", node_ids)


if __name__ == "__main__":
    unittest.main()
