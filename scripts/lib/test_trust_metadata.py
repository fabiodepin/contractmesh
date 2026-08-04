#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


from contractmesh.engine.trust_metadata import apply_trust_fields, infer_trust, trust_rank  # noqa: E402
from contractmesh.engine.adapters.null_adapter import load_edges  # noqa: E402


class TestTrustMetadata(unittest.TestCase):
    def test_contract_confirmed(self) -> None:
        st, tl = infer_trust("contract", "confirmed")
        self.assertEqual(st, "contract")
        self.assertEqual(tl, "confirmed")

    def test_contract_draft(self) -> None:
        _, tl = infer_trust("contract", "draft")
        self.assertEqual(tl, "draft")

    def test_rank_order(self) -> None:
        self.assertGreater(trust_rank("confirmed"), trust_rank("inferred"))

    def test_apply_fields(self) -> None:
        doc = apply_trust_fields({"kind": "code_anchor"})
        self.assertEqual(doc["trust_level"], "implementation")


class TestNullAdapter(unittest.TestCase):
    def test_empty_edges(self) -> None:
        self.assertEqual(load_edges(), [])


if __name__ == "__main__":
    unittest.main()
