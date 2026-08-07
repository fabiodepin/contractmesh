#!/usr/bin/env python3
"""Tests for .contractmeshignore support."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from contractmesh.engine.build_code_anchors import collect_code_anchors
from contractmesh.engine.build_search_index import RepoSpec, collect_repo_docs
from contractmesh.engine.contractmesh_ignore import load_contractmesh_ignore


class TestContractMeshIgnore(unittest.TestCase):
    def test_default_patterns_ignore_sensitive_and_generated_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            ignore = load_contractmesh_ignore(ws)
            self.assertTrue(ignore.ignores(".env"))
            self.assertTrue(ignore.ignores("services/api/secrets/token.md"))
            self.assertTrue(ignore.ignores("services/api/target/classes/App.class"))
            self.assertTrue(ignore.ignores("apps/web/debug.log"))
            self.assertTrue(ignore.ignores(".aws/credentials"))
            self.assertTrue(ignore.ignores("infra/prod.tfvars"))
            self.assertTrue(ignore.ignores(".venv/lib/python3.12/site-packages/pkg.py"))
            self.assertTrue(ignore.ignores("deploy/id_rsa"))
            self.assertFalse(ignore.ignores("services/api/docs/ai/contracts/public.md"))

    def test_repo_docs_skip_ignored_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            repo = ws / "services" / "billing-api"
            docs = repo / "docs" / "ai" / "contracts"
            docs.mkdir(parents=True)
            (ws / ".contractmeshignore").write_text("*secret*.md\n", encoding="utf-8")
            (docs / "public.md").write_text("# Public contract\n", encoding="utf-8")
            (docs / "secret-contract.md").write_text("# Secret contract\n", encoding="utf-8")
            (ws / "contractmesh.yml").write_text(
                """name: ignore-docs
mode: basic
workspace_mapping_version: v3
repos:
  - path: services/billing-api
    name: billing-api
docs:
  contracts: [docs/ai/contracts]
  adrs: [docs/adrs]
  gaps: [docs/known-gaps.md]
index:
  mode: allowlist
  include:
    - billing-api:docs/**
""",
                encoding="utf-8",
            )

            found = collect_repo_docs(ws, RepoSpec("billing-api", "services/billing-api"))
            rels = [rel for _path, rel in found]
            self.assertIn("services/billing-api/docs/ai/contracts/public.md", rels)
            self.assertNotIn("services/billing-api/docs/ai/contracts/secret-contract.md", rels)

    def test_code_anchors_skip_ignored_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            src = ws / "services" / "billing-api" / "src" / "main" / "java" / "demo"
            src.mkdir(parents=True)
            (ws / ".contractmeshignore").write_text("*SecretService.java\n", encoding="utf-8")
            (src / "PublicService.java").write_text(
                "package demo;\npublic class PublicService {}\n",
                encoding="utf-8",
            )
            (src / "SecretService.java").write_text(
                "package demo;\npublic class SecretService {}\n",
                encoding="utf-8",
            )
            (ws / "contractmesh.yml").write_text(
                """name: ignore-code
mode: basic
workspace_mapping_version: v3
repos:
  - path: services/billing-api
    name: billing-api
docs:
  contracts: [docs/contracts]
  adrs: [docs/adrs]
  gaps: [docs/known-gaps.md]
index:
  mode: allowlist
  include:
    - billing-api:src/**
""",
                encoding="utf-8",
            )

            entries, _counts, _trunc = collect_code_anchors(
                ws,
                ["billing-api=services/billing-api"],
                ws / ".contractmesh" / "index" / "chunks",
                {},
            )
            symbols = [manifest["symbol"] for manifest, _local, _n in entries]
            self.assertIn("PublicService", symbols)
            self.assertNotIn("SecretService", symbols)


if __name__ == "__main__":
    unittest.main()
