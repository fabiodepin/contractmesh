#!/usr/bin/env python3
"""Tests for build_code_anchors."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from contractmesh.engine.build_code_anchors import (
    anchor_id_for,
    extract_java_classes,
    extract_yaml_blocks,
    index_java_file,
)
from contractmesh.engine.chunk_ids import chunk_id_for, parse_chunk_id
from contractmesh.engine.workspace_search import is_symbol_partial_match


class TestAnchorId(unittest.TestCase):
    def test_anchor_id_includes_path_and_symbol(self) -> None:
        aid = anchor_id_for(
            "billing-api",
            "billing-api/src/main/java/foo/SubscriptionService.java",
            "SubscriptionService",
        )
        self.assertEqual(
            aid,
            "anchor:billing-api:billing-api/src/main/java/foo/SubscriptionService.java#SubscriptionService",
        )


class TestJavaExtract(unittest.TestCase):
    def test_extract_class_line(self) -> None:
        text = "package x;\n\npublic class SubscriptionService {\n}\n"
        classes = extract_java_classes(text)
        self.assertEqual(classes[0][0], "SubscriptionService")
        self.assertGreaterEqual(classes[0][1], 1)

    def test_service_impl_included(self) -> None:
        text = "public class SubscriptionServiceImpl implements SubscriptionService {\n}\n"
        classes = extract_java_classes(text)
        self.assertEqual(classes[0][0], "SubscriptionServiceImpl")


class TestYamlBlocks(unittest.TestCase):
    def test_extract_api_block(self) -> None:
        text = "server:\n  port: 8080\napi:\n  admin: http://localhost:8080\njwt:\n  secret: x\n"
        blocks = extract_yaml_blocks(text)
        keys = [k for k, _ in blocks]
        self.assertIn("api", keys)
        self.assertIn("jwt", keys)


class TestSymbolPartial(unittest.TestCase):
    def test_impl_partial(self) -> None:
        self.assertTrue(
            is_symbol_partial_match("SubscriptionService", "SubscriptionServiceImpl")
        )
        self.assertFalse(
            is_symbol_partial_match("SubscriptionService", "SubscriptionService")
        )


class TestIndexJavaFile(unittest.TestCase):
    def test_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            repo = "demo-api"
            rel = f"{repo}/src/main/java/demo/SubscriptionService.java"
            java_path = ws / rel
            java_path.parent.mkdir(parents=True)
            java_path.write_text(
                "package demo;\n@Service\npublic class SubscriptionService {\n  public void x() {}\n}\n",
                encoding="utf-8",
            )
            chunks = ws / ".contractmesh" / "index" / "chunks"
            entries = index_java_file(ws, java_path, rel, repo, chunks, {}, 58)
            self.assertEqual(len(entries), 1)
            manifest, _local, n = entries[0]
            self.assertEqual(manifest["kind"], "code_anchor")
            self.assertEqual(manifest["symbol"], "SubscriptionService")
            self.assertTrue(manifest["id"].startswith("anchor:"))
            self.assertIn("#SubscriptionService", manifest["id"])
            self.assertEqual(n, 1)

    def test_chunk_id_suffix_is_zero_not_symbol(self) -> None:
        doc_id = anchor_id_for(
            "billing-api",
            "billing-api/src/main/java/foo/SubscriptionController.java",
            "SubscriptionController",
        )
        self.assertEqual(
            chunk_id_for(doc_id, 0),
            f"{doc_id}#0",
        )
        parsed_doc_id, idx = parse_chunk_id(chunk_id_for(doc_id, 0))
        self.assertEqual(parsed_doc_id, doc_id)
        self.assertEqual(idx, "0")


if __name__ == "__main__":
    unittest.main()
