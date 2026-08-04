#!/usr/bin/env python3
"""Tests for preflight_change (basic fixture)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


from contractmesh.engine.preflight_change import parse_symbol_target, preflight_change  # noqa: E402
from .test_fixture_support import ensure_basic_fixture_index, fixture_manifest_path  # noqa: E402
from contractmesh.engine.workspace_search import load_index  # noqa: E402


class TestParseSymbolTarget(unittest.TestCase):
    def test_class_only(self) -> None:
        self.assertEqual(parse_symbol_target("ExampleService"), ("ExampleService", None))

    def test_class_and_method(self) -> None:
        self.assertEqual(
            parse_symbol_target("ExampleService.greet"),
            ("ExampleService", "greet"),
        )


class TestPreflightChangeIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace = ensure_basic_fixture_index()
        if not fixture_manifest_path().is_file():
            raise unittest.SkipTest("basic fixture index missing")
        cls.manifest, cls.local = load_index(cls.workspace)

    def test_example_service_preflight(self) -> None:
        result, err = preflight_change(
            self.workspace,
            self.manifest,
            self.local,
            symbol="ExampleService.greet",
            repo=["app"],
        )
        self.assertIsNone(err)
        card = result["card"]
        details = result["details"]
        self.assertEqual(details["class_symbol"], "ExampleService")
        self.assertEqual(details["method"], "greet")
        self.assertIn(card["risk"], {"HIGH", "MEDIUM", "LOW"})
        self.assertIn("Risk:", card["text"])


if __name__ == "__main__":
    unittest.main()
