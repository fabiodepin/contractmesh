#!/usr/bin/env python3
"""Tests for chunk_id parsing (anchor doc_ids contain '#')."""

from __future__ import annotations

import unittest

from contractmesh.engine.chunk_ids import chunk_id_for, parse_chunk_id


class TestChunkIds(unittest.TestCase):
    def test_doc_chunk_id(self) -> None:
        doc_id = "doc:billing-api:docs:ai:contracts:subscriptions"
        self.assertEqual(chunk_id_for(doc_id, 2), f"{doc_id}#2")

    def test_anchor_chunk_id_explicit_suffix(self) -> None:
        doc_id = (
            "anchor:billing-api:billing-api/src/main/java/foo/SubscriptionController.java"
            "#SubscriptionController"
        )
        chunk_id = chunk_id_for(doc_id, 0)
        self.assertEqual(
            chunk_id,
            "anchor:billing-api:billing-api/src/main/java/foo/SubscriptionController.java"
            "#SubscriptionController#0",
        )

    def test_parse_anchor_uses_rsplit(self) -> None:
        chunk_id = (
            "anchor:billing-api:billing-api/src/main/java/foo/SubscriptionController.java"
            "#SubscriptionController#0"
        )
        doc_id, index = parse_chunk_id(chunk_id)
        self.assertEqual(index, "0")
        self.assertTrue(doc_id.endswith("#SubscriptionController"))
        self.assertNotEqual(
            doc_id,
            "anchor:billing-api:billing-api/src/main/java/foo/SubscriptionController.java",
        )


if __name__ == "__main__":
    unittest.main()
