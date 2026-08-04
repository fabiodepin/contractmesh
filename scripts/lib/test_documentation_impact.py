#!/usr/bin/env python3
"""Tests for documentation_impact: none / possible / confirmed."""

from __future__ import annotations

import unittest

from contractmesh.engine.documentation_impact import (
    CONFIRMATION_SEMANTIC,
    CONFIRMATION_STRUCTURAL,
    EVIDENCE_ANCHOR_UNRESOLVED,
    EVIDENCE_KNOWN_GAP_AFFECTED,
    EVIDENCE_LINKED_SYMBOL_CHANGED,
    EVIDENCE_RELATED_TEST_CHANGED,
    EVIDENCE_SEMANTIC_MISMATCH,
    STATE_CONFIRMED,
    STATE_NONE,
    STATE_POSSIBLE,
    compute_documentation_impact,
    core_documentation_impact,
    format_documentation_impact,
)


def _manifest() -> dict:
    auth_contract = {
        "id": "doc:app:auth",
        "repo": "app",
        "path": "docs/contracts/api-auth.md",
        "kind": "contract",
        "title": "Unified authentication",
        "external_id": "API-AUTH-CONTRACT-001",
        "related_anchors": ["AuthLoginService", "TokenIssuer"],
        "code_anchors": [
            "anchor:app:src/AuthLoginService.py#AuthLoginService",
            "anchor:app:src/TokenIssuer.py#TokenIssuer",
        ],
        "known_gap_ids": ["GAP-AUTH-003"],
    }
    billing_contract = {
        "id": "doc:app:billing",
        "repo": "app",
        "path": "docs/contracts/billing.md",
        "kind": "contract",
        "title": "Billing invoices",
        "external_id": "BILL-CONTRACT-001",
        "related_anchors": ["InvoiceService"],
        "code_anchors": ["anchor:app:src/InvoiceService.py#InvoiceService"],
        "known_gap_ids": [],
    }
    auth_login = {
        "id": "anchor:app:src/AuthLoginService.py#AuthLoginService",
        "repo": "app",
        "path": "src/AuthLoginService.py",
        "kind": "code_anchor",
        "symbol": "AuthLoginService",
        "anchor_type": "service",
        "related_doc_ids": ["doc:app:auth"],
    }
    token = {
        "id": "anchor:app:src/TokenIssuer.py#TokenIssuer",
        "repo": "app",
        "path": "src/TokenIssuer.py",
        "kind": "code_anchor",
        "symbol": "TokenIssuer",
        "anchor_type": "service",
        "related_doc_ids": ["doc:app:auth"],
    }
    invoice = {
        "id": "anchor:app:src/InvoiceService.py#InvoiceService",
        "repo": "app",
        "path": "src/InvoiceService.py",
        "kind": "code_anchor",
        "symbol": "InvoiceService",
        "anchor_type": "service",
        "related_doc_ids": ["doc:app:billing"],
    }
    login_test = {
        "id": "anchor:app:tests/auth/test_login.py#test_login",
        "repo": "app",
        "path": "tests/auth/test_login.py",
        "kind": "test_anchor",
        "symbol": "test_login_AuthLoginService",
        "anchor_type": "test",
        "related_doc_ids": ["doc:app:auth"],
    }
    return {
        "documents": [
            auth_contract,
            billing_contract,
            auth_login,
            token,
            invoice,
            login_test,
        ]
    }


class TestDocumentationImpact(unittest.TestCase):
    def test_none_when_unrelated_code_changes(self) -> None:
        """False positive guard: unrelated file → silence."""
        result = compute_documentation_impact(
            changed_paths=["src/UnrelatedHelper.py"],
            manifest=_manifest(),
        )
        self.assertEqual(result["state"], STATE_NONE)
        self.assertEqual(result["documents"], [])
        self.assertIsNone(result["summary"])
        self.assertIsNone(format_documentation_impact(result))

    def test_none_when_code_and_linked_doc_both_changed(self) -> None:
        result = compute_documentation_impact(
            changed_paths=[
                "src/AuthLoginService.py",
                "docs/contracts/api-auth.md",
            ],
            manifest=_manifest(),
        )
        self.assertEqual(result["state"], STATE_NONE)

    def test_possible_when_linked_symbol_changed_without_doc(self) -> None:
        result = compute_documentation_impact(
            changed_paths=["src/AuthLoginService.py", "src/TokenIssuer.py"],
            manifest=_manifest(),
        )
        self.assertEqual(result["state"], STATE_POSSIBLE)
        self.assertEqual(result["enforcement"], "advisory")
        self.assertIsNone(result["confirmation_kind"])
        self.assertNotEqual(result["confidence"], "confirmed")  # confidence != state
        docs = result["documents"]
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["id"], "API-AUTH-CONTRACT-001")
        kinds = {r["kind"] for r in docs[0]["reasons"]}
        self.assertIn(EVIDENCE_LINKED_SYMBOL_CHANGED, kinds)
        self.assertIn(EVIDENCE_KNOWN_GAP_AFFECTED, kinds)
        # Provenance on linked_symbol reasons
        linked = next(r for r in docs[0]["reasons"] if r["kind"] == EVIDENCE_LINKED_SYMBOL_CHANGED)
        self.assertIn("source", linked)
        self.assertEqual(linked["source"].get("symbol"), "AuthLoginService")
        # Must never be confirmed solely from code-without-doc.
        self.assertNotEqual(result["state"], STATE_CONFIRMED)

    def test_possible_with_related_tests(self) -> None:
        result = compute_documentation_impact(
            changed_paths=[
                "src/AuthLoginService.py",
                "tests/auth/test_login.py",
            ],
            manifest=_manifest(),
        )
        self.assertEqual(result["state"], STATE_POSSIBLE)
        kinds = {r["kind"] for r in result["documents"][0]["reasons"]}
        self.assertIn(EVIDENCE_RELATED_TEST_CHANGED, kinds)
        self.assertIn(result["confidence"], ("medium", "high"))
        text = format_documentation_impact(result)
        self.assertIsNotNone(text)
        self.assertIn("API-AUTH-CONTRACT-001", text or "")

    def test_confirmed_requires_demonstrable_evidence(self) -> None:
        result = compute_documentation_impact(
            changed_paths=["src/AuthLoginService.py"],
            manifest=_manifest(),
            confirmed_findings=[
                {
                    "drift_type": "semantic_mismatch",
                    "summary": "Contract declares 401 but implementation returns 403",
                    "external_id": "API-AUTH-CONTRACT-001",
                    "path": "src/AuthLoginService.py",
                    "symbol": "AuthLoginService",
                    "line": 84,
                    "repo": "app",
                }
            ],
        )
        self.assertEqual(result["state"], STATE_CONFIRMED)
        self.assertEqual(result["enforcement"], "soft_block")
        self.assertEqual(result["confirmation_kind"], CONFIRMATION_SEMANTIC)
        kinds = {r["kind"] for r in result["documents"][0]["reasons"]}
        self.assertIn(EVIDENCE_SEMANTIC_MISMATCH, kinds)
        sem = next(r for r in result["documents"][0]["reasons"] if r["kind"] == EVIDENCE_SEMANTIC_MISMATCH)
        self.assertEqual(sem["source"]["line"], 84)

    def test_anchor_unresolved_is_confirmed_structural(self) -> None:
        result = compute_documentation_impact(
            changed_paths=["src/AuthLoginService.py"],
            manifest=_manifest(),
            confirmed_findings=[
                {
                    "drift_type": "anchor_unresolved",
                    "summary": "Contract references anchor 'AuthLoginService' not found",
                }
            ],
        )
        self.assertEqual(result["state"], STATE_CONFIRMED)
        self.assertEqual(result["confirmation_kind"], CONFIRMATION_STRUCTURAL)
        reason = next(
            r
            for r in result["documents"][0]["reasons"]
            if r["kind"] == EVIDENCE_ANCHOR_UNRESOLVED
        )
        self.assertEqual(reason.get("classification"), "confirmed_structural")

    def test_linked_symbol_alone_never_confirmed(self) -> None:
        result = compute_documentation_impact(
            changed_paths=["src/InvoiceService.py"],
            manifest=_manifest(),
        )
        self.assertEqual(result["state"], STATE_POSSIBLE)
        kinds = {r["kind"] for doc in result["documents"] for r in doc["reasons"]}
        self.assertEqual(kinds, {EVIDENCE_LINKED_SYMBOL_CHANGED})

    def test_core_payload_stable_across_wrappers(self) -> None:
        """Engine core equals git wrapper / alias / pr_impact embedded payload."""
        from pathlib import Path

        from contractmesh.engine.documentation_impact import DEPRECATION_DOCS_DRIFT_CHECK
        from contractmesh.engine.git_workspace_tools import documentation_impact

        paths = ["src/AuthLoginService.py"]
        engine = compute_documentation_impact(changed_paths=paths, manifest=_manifest())
        wrapped, err = documentation_impact(Path("."), _manifest(), changed_paths=paths)
        self.assertIsNone(err)
        self.assertEqual(core_documentation_impact(engine), core_documentation_impact(wrapped))

        alias_payload = {**DEPRECATION_DOCS_DRIFT_CHECK, "documentation_impact": wrapped}
        self.assertTrue(alias_payload["deprecated"])
        self.assertEqual(alias_payload["replacement"], "documentation_impact")
        self.assertEqual(
            core_documentation_impact(engine),
            core_documentation_impact(alias_payload["documentation_impact"]),
        )

        pr_style = {"documentation_impact": engine}
        self.assertEqual(
            core_documentation_impact(engine),
            core_documentation_impact(pr_style["documentation_impact"]),
        )


if __name__ == "__main__":
    unittest.main()
