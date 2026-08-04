#!/usr/bin/env python3
"""Unit tests for impact_analysis seed filtering and related expansion."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from contractmesh.engine.workspace_search import (  # noqa: E402
    SearchHit,
    _expand_related_contract_docs,
    _filter_hits_by_relative_score,
    _token_idf_weights,
    impact_analysis,
    score_document,
    significant_query_tokens,
)


def _hit(doc_id: str, score: int, path: str = "") -> SearchHit:
    return SearchHit(
        score=score,
        doc_id=doc_id,
        repo="app",
        path=path or f"docs/{doc_id}.md",
        kind="contract",
        domain=None,
        title=doc_id,
        heading=None,
        known_gap_ids=[],
        snippet="",
        top_chunk_ids=[],
    )


def _contract(
    doc_id: str,
    *,
    title: str,
    external_id: str,
    related: list[str] | None = None,
    keywords: list[str] | None = None,
    gaps: list[str] | None = None,
) -> dict:
    return {
        "id": doc_id,
        "repo": "app",
        "path": f"docs/contracts/{doc_id}.md",
        "kind": "contract",
        "title": title,
        "keywords": keywords or [],
        "headings": [],
        "external_id": external_id,
        "related_contracts": related or [],
        "known_gap_ids": gaps or [],
        "trust_level": "confirmed",
        "weight": 10,
        "code_anchors": [],
    }


class TestImpactAnalysisNoise(unittest.TestCase):
    def test_significant_tokens_drop_stopwords(self) -> None:
        tokens = significant_query_tokens("What changes if login rules change?")
        self.assertEqual(tokens, ["login"])

    def test_relative_score_floor_keeps_near_top_only(self) -> None:
        hits = [
            _hit("auth", 40),
            _hit("billing", 34),
            _hit("mailbox", 28),
            _hit("noise", 20),
        ]
        kept = _filter_hits_by_relative_score(hits)
        ids = [h.doc_id for h in kept]
        self.assertEqual(ids, ["auth", "billing"])

    def test_soft_idf_prefers_distinctive_tokens(self) -> None:
        docs = [
            _contract("auth", title="Unified login authentication", external_id="AUTH-1"),
            _contract("tenant", title="Tenant lifecycle", external_id="TENANT-1"),
            _contract("domain", title="Tenant email domain registry", external_id="DOMAIN-1"),
            _contract("mailbox", title="Mailbox provisioning", external_id="MAIL-1"),
        ]
        tokens = ["unified", "login", "tenant", "email", "domain"]
        weights = _token_idf_weights(docs, tokens)
        self.assertGreater(weights["login"], weights["tenant"])

        auth = score_document(docs[0], tokens, None, None, weights)
        tenant = score_document(docs[1], tokens, None, None, weights)
        self.assertGreater(auth, tenant)

    def test_related_expansion_from_primary_only(self) -> None:
        auth = _contract(
            "auth",
            title="Login authentication",
            external_id="AUTH-1",
            related=["FE-AUTH-1", "MT-1"],
        )
        tenant = _contract(
            "tenant",
            title="Tenant lifecycle",
            external_id="TENANT-1",
            related=["MAIL-1", "AUTH-1"],
        )
        fe = _contract("fe-auth", title="Frontend login client", external_id="FE-AUTH-1")
        mt = _contract("mt", title="Tenant isolation", external_id="MT-1")
        mailbox = _contract("mailbox", title="Mailbox email lifecycle", external_id="MAIL-1")
        manifest = {"documents": [auth, tenant, fe, mt, mailbox]}

        expanded = _expand_related_contract_docs(
            manifest,
            [tenant],
            query_tokens=["login", "authentication", "tenant"],
            primary_limit=1,
            related_limit=3,
        )
        ids = {d["id"] for d in expanded}
        self.assertIn("auth", ids)
        self.assertIn("fe-auth", ids)
        self.assertNotIn("mailbox", ids)

    def test_impact_analysis_does_not_cascade_unrelated_contracts(self) -> None:
        auth = _contract(
            "auth",
            title="Unified login authentication",
            external_id="AUTH-1",
            related=["FE-AUTH-1"],
            keywords=["login", "unified", "authentication"],
            gaps=["APP-KG-AUTH-001"],
        )
        fe = _contract(
            "fe-auth",
            title="Frontend login client",
            external_id="FE-AUTH-1",
            keywords=["login", "frontend"],
        )
        tenant = _contract(
            "tenant",
            title="Tenant subscription lifecycle",
            external_id="TENANT-1",
            related=["BILLING-1"],
            keywords=["tenant", "subscription"],
        )
        billing = _contract(
            "billing",
            title="Billing invoices",
            external_id="BILLING-1",
            keywords=["billing", "invoice"],
            gaps=["APP-KG-BILL-001"],
        )
        mailbox = _contract(
            "mailbox",
            title="Mailbox provisioning",
            external_id="MAIL-1",
            keywords=["mailbox", "email"],
            gaps=["APP-KG-MAIL-001"],
        )
        gaps_doc = {
            "id": "gaps",
            "repo": "app",
            "path": "docs/known-gaps.md",
            "kind": "known_gaps",
            "title": "Known gaps",
            "keywords": [],
            "headings": [],
            "known_gap_ids": ["APP-KG-AUTH-001", "APP-KG-BILL-001", "APP-KG-MAIL-001"],
            "trust_level": "confirmed",
            "weight": 5,
        }
        manifest = {"documents": [auth, fe, tenant, billing, mailbox, gaps_doc]}
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result, err = impact_analysis(
                workspace,
                manifest,
                {},
                query="unified login authentication",
                limit=8,
            )
        self.assertIsNone(err)
        contract_paths = [c["path"] for c in result["contracts"]]
        self.assertTrue(any("auth" in p for p in contract_paths))
        self.assertFalse(any("mailbox" in p for p in contract_paths))
        self.assertFalse(any("billing" in p for p in contract_paths))
        # Contracts with gaps must not be duplicated into known_gaps.
        gap_kinds = {g.get("kind") for g in result["known_gaps"]}
        self.assertTrue(not gap_kinds or gap_kinds == {"known_gaps"})


if __name__ == "__main__":
    unittest.main()
