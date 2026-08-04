#!/usr/bin/env python3
"""Tests for contract <-> code_anchor cross-linking."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from contractmesh.engine.build_contract_crosslinks import (
    CROSSLINK_SOURCE_KINDS,
    RELATED_ANCHORS_SEARCH_LIMIT,
    apply_contract_crosslinks,
    build_related_anchors_for_hit,
    extract_symbols_from_text,
    resolve_anchor_ids,
)
from contractmesh.engine.workspace_search import SearchHit, search_hit_to_dict


class TestCrosslinkSourceKinds(unittest.TestCase):
    def test_source_kinds_include_contract_architecture_integrations_and_adr(self) -> None:
        self.assertEqual(
            CROSSLINK_SOURCE_KINDS,
            frozenset({"contract", "architecture", "integrations", "adr"}),
        )


class TestExtractSymbols(unittest.TestCase):
    def test_backticks_skip_payload(self) -> None:
        text = "Use `SubscriptionController` and `CreateSubscriptionPayload` for `SubscriptionService`."
        self.assertEqual(
            extract_symbols_from_text(text),
            ["SubscriptionController", "SubscriptionService"],
        )

    def test_prose_service_without_backticks(self) -> None:
        text = "SubscriptionService calls other services."
        syms = extract_symbols_from_text(text)
        self.assertIn("SubscriptionService", syms)

    def test_architecture_kind_in_source_kinds(self) -> None:
        self.assertIn("architecture", CROSSLINK_SOURCE_KINDS)


class TestCaseSensitiveResolve(unittest.TestCase):
    def test_exact_only(self) -> None:
        index = {("billing-api", "SubscriptionService"): ["anchor-1"]}
        self.assertEqual(
            resolve_anchor_ids("billing-api", "SubscriptionService", index),
            ["anchor-1"],
        )
        self.assertEqual(
            resolve_anchor_ids("billing-api", "subscriptionservice", index), []
        )


class TestCrossRepoContractLinks(unittest.TestCase):
    def test_workspace_level_contract_links_backend_symbol(self) -> None:
        """Workspace-root docs (repo=workspace name) resolve anchors in other repos."""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            rel = "docs/contracts/subscriptions.md"
            contract_path = ws / rel
            contract_path.parent.mkdir(parents=True)
            contract_path.write_text(
                "---\nrelated_anchors:\n  - SubscriptionService\n---\n"
                "See `SubscriptionService` and `BillingResolver`.\n",
                encoding="utf-8",
            )
            contract_id = "doc:acme-workspace:docs:contracts:subscriptions"
            anchor_id = (
                "anchor:billing-api:billing-api/src/SubscriptionService.java"
                "#SubscriptionService"
            )
            manifest_docs = [
                {
                    "id": contract_id,
                    "repo": "acme-workspace",
                    "path": rel,
                    "kind": "contract",
                    "related_anchors": ["SubscriptionService", "BillingResolver"],
                    "links": {"related": []},
                },
                {
                    "id": anchor_id,
                    "repo": "billing-api",
                    "path": "billing-api/src/SubscriptionService.java",
                    "kind": "code_anchor",
                    "symbol": "SubscriptionService",
                    "anchor_type": "service",
                },
            ]
            stats = apply_contract_crosslinks(ws, manifest_docs)
            self.assertEqual(stats.contracts_with_code_anchors, 1)
            self.assertIn(anchor_id, manifest_docs[0]["code_anchors"])
            self.assertIn(contract_id, manifest_docs[1]["related_doc_ids"])
            # BillingResolver has no anchor → counted unresolved
            self.assertGreaterEqual(stats.contract_symbols_unresolved_unique, 1)


class TestApplyCrosslinks(unittest.TestCase):
    def test_bidirectional_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            repo = "billing-api"
            rel = f"{repo}/docs/ai/contracts/subscriptions.md"
            contract_path = ws / rel
            contract_path.parent.mkdir(parents=True)
            contract_path.write_text(
                "See `SubscriptionController`. SubscriptionService runs jobs.\n",
                encoding="utf-8",
            )

            contract_id = "doc:billing-api:docs:ai:contracts:subscriptions"
            anchor_tc = (
                "anchor:billing-api:src/SubscriptionController.java"
                "#SubscriptionController"
            )
            anchor_ts = (
                "anchor:billing-api:src/SubscriptionService.java"
                "#SubscriptionService"
            )

            manifest_docs = [
                {
                    "id": contract_id,
                    "repo": repo,
                    "path": rel,
                    "kind": "contract",
                    "links": {"related": []},
                },
                {
                    "id": anchor_tc,
                    "repo": repo,
                    "path": "billing-api/src/SubscriptionController.java",
                    "kind": "code_anchor",
                    "symbol": "SubscriptionController",
                    "anchor_type": "controller",
                    "line_start": 10,
                    "line_end": 40,
                },
                {
                    "id": anchor_ts,
                    "repo": repo,
                    "path": "billing-api/src/SubscriptionService.java",
                    "kind": "code_anchor",
                    "symbol": "SubscriptionService",
                    "anchor_type": "service",
                },
                {
                    "id": "doc:billing-api:docs:ai:architecture",
                    "repo": repo,
                    "path": f"{repo}/docs/ai/architecture.md",
                    "kind": "architecture",
                },
                {
                    "id": "anchor:billing-api:src/SomeService.java#SomeService",
                    "repo": repo,
                    "path": "billing-api/src/SomeService.java",
                    "kind": "code_anchor",
                    "symbol": "SomeService",
                    "anchor_type": "service",
                },
            ]
            arch_path = ws / f"{repo}/docs/ai/architecture.md"
            arch_path.parent.mkdir(parents=True, exist_ok=True)
            arch_path.write_text("`SomeService`", encoding="utf-8")

            stats = apply_contract_crosslinks(ws, manifest_docs)
            self.assertEqual(stats.contracts_with_code_anchors, 2)
            self.assertGreaterEqual(stats.anchors_with_related_doc_ids, 2)

            contract = manifest_docs[0]
            self.assertIn(anchor_tc, contract["code_anchors"])
            self.assertIn(anchor_ts, contract["code_anchors"])

            arch_doc = manifest_docs[3]
            self.assertIn(
                "anchor:billing-api:src/SomeService.java#SomeService",
                arch_doc["code_anchors"],
            )

            by_id = {d["id"]: d for d in manifest_docs}
            anchor = by_id[anchor_tc]
            self.assertIn(contract_id, anchor["related_doc_ids"])


class TestRelatedAnchorsSearch(unittest.TestCase):
    def test_truncation_and_count(self) -> None:
        anchor_ids = [f"anchor:r:p{i}.java#Sym{i}" for i in range(20)]
        by_id = {
            aid: {
                "id": aid,
                "path": f"r/src/{aid.split('#')[-1]}.java",
                "symbol": aid.split("#")[-1],
                "anchor_type": "service",
                "line_start": idx,
                "line_end": idx + 10,
            }
            for idx, aid in enumerate(anchor_ids)
        }
        doc = {"code_anchors": anchor_ids}
        total, items = build_related_anchors_for_hit(doc, by_id)
        self.assertEqual(total, 20)
        self.assertEqual(len(items), RELATED_ANCHORS_SEARCH_LIMIT)
        self.assertIn("line_start", items[0])
        self.assertIn("line_end", items[0])

    def test_ranks_controller_and_service_before_entity(self) -> None:
        by_id = {
            "a-entity": {
                "id": "a-entity",
                "path": "src/User.java",
                "symbol": "User",
                "anchor_type": "entity",
            },
            "a-svc": {
                "id": "a-svc",
                "path": "src/AuthLoginService.java",
                "symbol": "AuthLoginService",
                "anchor_type": "service",
            },
            "a-ctl": {
                "id": "a-ctl",
                "path": "src/AuthController.java",
                "symbol": "AuthController",
                "anchor_type": "controller",
            },
        }
        doc = {
            "related_anchors": ["AuthController", "AuthLoginService"],
            "code_anchors": ["a-entity", "a-svc", "a-ctl"],
        }
        _total, items = build_related_anchors_for_hit(doc, by_id, limit=2)
        self.assertEqual(
            [i["symbol"] for i in items],
            ["AuthController", "AuthLoginService"],
        )

    def test_search_hit_dict_includes_related(self) -> None:
        hit = SearchHit(
            score=100,
            doc_id="doc:x",
            repo="billing-api",
            path="billing-api/docs/ai/contracts/subscriptions.md",
            kind="contract",
            domain=None,
            title="subscriptions",
            heading=None,
            known_gap_ids=[],
            snippet="",
            top_chunk_ids=["doc:x#0"],
            related_anchor_count=15,
            related_anchors=[
                {
                    "doc_id": "anchor:a",
                    "path": "billing-api/src/A.java",
                    "symbol": "A",
                    "top_chunk_ids": ["anchor:a#0"],
                }
            ],
        )
        d = search_hit_to_dict(hit)
        self.assertEqual(d["related_anchor_count"], 15)
        self.assertEqual(len(d["related_anchors"]), 1)


if __name__ == "__main__":
    unittest.main()
