#!/usr/bin/env python3
"""Tests for fetch_hits and enriched index_status (basic fixture)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


from .test_fixture_support import ensure_basic_fixture_index, fixture_manifest_path  # noqa: E402
from contractmesh.engine.workspace_search import (  # noqa: E402
    cross_repo_keyword_boost,
    fetch_hits,
    gap_id_prefix,
    impact_analysis,
    index_status,
    load_index,
    related_tests,
    recommend_index_rebuild,
)


class TestFetchHitsHelpers(unittest.TestCase):
    def test_gap_id_prefix(self) -> None:
        self.assertEqual(gap_id_prefix("APP-KG-001"), "APP-KG")

    def test_cross_repo_boost(self) -> None:
        doc = {"repo": "app", "kind": "contract"}
        self.assertGreater(cross_repo_keyword_boost(doc, ["app"]), 0)
        self.assertEqual(cross_repo_keyword_boost(doc, ["unrelated"]), 0)

    def test_recommend_rebuild(self) -> None:
        self.assertTrue(recommend_index_rebuild(age_hours=50, missing_chunks=0))
        self.assertTrue(recommend_index_rebuild(age_hours=1, missing_chunks=1))
        self.assertFalse(recommend_index_rebuild(age_hours=1, missing_chunks=0))


class TestFetchHitsIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace = ensure_basic_fixture_index()
        if not fixture_manifest_path().is_file():
            raise unittest.SkipTest("basic fixture index missing")

    def test_fetch_hits_example_contract(self) -> None:
        manifest, local_by_id = load_index(self.workspace)
        result, err = fetch_hits(
            self.workspace,
            manifest,
            local_by_id,
            query="ExampleService example application",
            kind=["contract"],
            repo=["app"],
            limit=1,
        )
        self.assertIsNone(err)
        self.assertGreaterEqual(result["count"], 1)
        hit = result["hits"][0]
        self.assertIn("example-contract", hit["path"])
        self.assertIn("chunk", hit)

    def test_fetch_hits_gap(self) -> None:
        manifest, local_by_id = load_index(self.workspace)
        result, err = fetch_hits(
            self.workspace,
            manifest,
            local_by_id,
            gap="APP-KG-001",
            limit=2,
        )
        self.assertIsNone(err)
        self.assertGreaterEqual(result["count"], 1)

    def test_index_status_enriched(self) -> None:
        st = index_status(self.workspace, deep=False)
        self.assertTrue(st["manifest_exists"])
        self.assertIn("generated_at_age_hours", st)
        self.assertIn("recommend_rebuild", st)
        self.assertIn("openapi_enabled", st)
        self.assertIn("embeddings_enabled", st)
        self.assertIn(st.get("embedding_status"), ("disabled", "pending", "partial", "ready", None))

    def test_related_tests_by_symbol(self) -> None:
        manifest, local_by_id = load_index(self.workspace)
        result, err = related_tests(
            self.workspace,
            manifest,
            local_by_id,
            symbol="ExampleService",
            repo=["app"],
        )
        self.assertIsNone(err)
        self.assertGreaterEqual(result["count"], 1)
        paths = [t["path"] for t in result["related_tests"]]
        self.assertTrue(any("test_example" in p for p in paths))

    def test_impact_analysis_returns_change_evidence(self) -> None:
        manifest, local_by_id = load_index(self.workspace)
        result, err = impact_analysis(
            self.workspace,
            manifest,
            local_by_id,
            query="ExampleService greeting behavior",
            repo=["app"],
        )
        self.assertIsNone(err)
        self.assertTrue(result["contracts"])
        self.assertTrue(result["code_anchors"])
        self.assertLessEqual(len(result["code_anchors"]), 12)
        self.assertIn("sources_consulted", result["provenance"])


if __name__ == "__main__":
    unittest.main()
