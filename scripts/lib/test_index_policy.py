#!/usr/bin/env python3
"""Tests for index allowlist/denylist security policy."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from contractmesh.engine.build_code_anchors import collect_code_anchors
from contractmesh.engine.build_search_index import RepoSpec, collect_repo_docs, collect_workspace_docs
from contractmesh.engine.build_structural_graph import collect_structural_edges
from contractmesh.engine.index_policy import (
    compile_pattern,
    load_index_policy,
    validate_index_security,
)
from contractmesh.engine.workspace_manifest import load_workspace_manifest, validate_manifest
from contractmesh.engine.workspace_search import run_build


DEFAULT_ALLOWLIST_BLOCK = """index:
  mode: allowlist
  include:
    - src/**
    - tests/**
    - docs/**
    - README.md
"""


def _write_basic(ws: Path, *, index_block: str | None = None) -> None:
    if index_block is None:
        index_block = DEFAULT_ALLOWLIST_BLOCK
    (ws / "docs" / "contracts").mkdir(parents=True)
    (ws / "docs" / "adrs").mkdir(parents=True)
    (ws / "src").mkdir(parents=True)
    (ws / "tests").mkdir(parents=True)
    (ws / "secrets").mkdir(parents=True)
    (ws / "docs" / "contracts" / "example-contract.md").write_text(
        "---\nid: APP-CONTRACT-001\nstatus: confirmed\n"
        "owner:\n  team: example\n  service: app\nrelated_anchors:\n  - ExampleService\n---\n"
        "# Example\n",
        encoding="utf-8",
    )
    (ws / "docs" / "known-gaps.md").write_text("# Gaps\n", encoding="utf-8")
    (ws / "docs" / "adrs" / "example-adr.md").write_text(
        "---\nid: APP-ADR-001\nstatus: accepted\n"
        "owner:\n  team: example\n  service: app\n---\n# ADR\n",
        encoding="utf-8",
    )
    (ws / "src" / "example.py").write_text(
        "class ExampleService:\n    def greet(self):\n        return 'hi'\n",
        encoding="utf-8",
    )
    (ws / "src" / "hidden_util.py").write_text("class HiddenUtil:\n    pass\n", encoding="utf-8")
    (ws / "secrets" / "leak.py").write_text("class SecretLeak:\n    pass\n", encoding="utf-8")
    (ws / "tests" / "test_example.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )
    (ws / ".contractmeshignore").write_text("*.pem\n", encoding="utf-8")
    (ws / "contractmesh.yml").write_text(
        f"""name: policy-test
mode: basic
workspace_mapping_version: v3
repos:
  - path: .
    name: app
docs:
  contracts:
    - docs/contracts
  adrs:
    - docs/adrs
  gaps:
    - docs/known-gaps.md
lint:
  require_owner: false
  require_ids: false
  require_valid_crosslinks: false
{index_block}
""",
        encoding="utf-8",
    )


class TestGlobCompile(unittest.TestCase):
    def test_double_star_and_basename(self) -> None:
        nested = compile_pattern("src/**/*.py")
        self.assertTrue(nested.regex.match("src/a/b.py"))
        self.assertFalse(nested.regex.match("tests/a.py"))
        base = compile_pattern("*.pem")
        self.assertTrue(base.regex.match("certs/server.pem"))
        self.assertTrue(base.regex.match("server.pem"))


class TestIndexPolicy(unittest.TestCase):
    def test_missing_mode_fails_validation(self) -> None:
        errors = validate_index_security({"include": ["src/**"]})
        self.assertTrue(any("index.mode is required" in e for e in errors))
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            _write_basic(ws, index_block="")  # no index block at all
            manifest = load_workspace_manifest(ws)
            errs = validate_manifest(ws, manifest)
            self.assertTrue(any("index.mode is required" in e for e in errs))
            with self.assertRaises(ValueError):
                load_index_policy(ws, manifest)

    def test_explicit_denylist_is_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            _write_basic(
                ws,
                index_block="""index:
  mode: denylist
""",
            )
            policy = load_index_policy(ws)
            self.assertEqual(policy.mode, "denylist")
            self.assertTrue(policy.allows("src/example.py", count=False))
            # denylist indexes undeclared paths (unlike allowlist), unless ignored.
            self.assertTrue(policy.allows("other/unlisted.py", count=False))
            self.assertFalse(policy.allows("secrets/leak.py", count=False))  # ignore layer
            self.assertFalse(policy.allows(".env", count=False))

    def test_allowlist_fail_closed_validation(self) -> None:
        errors = validate_index_security({"mode": "allowlist", "include": []})
        self.assertTrue(any("non-empty index.include" in e for e in errors))

    def test_allowlist_include_exclude_and_ignore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            _write_basic(
                ws,
                index_block="""index:
  mode: allowlist
  include:
    - src/**
    - docs/contracts/**
    - docs/adrs/**
    - docs/known-gaps.md
    - tests/**
  exclude:
    - src/hidden_util.py
""",
            )
            (ws / "keep.pem").write_text("x", encoding="utf-8")
            policy = load_index_policy(ws)
            self.assertTrue(policy.allows("src/example.py", count=False))
            self.assertFalse(policy.allows("src/hidden_util.py", count=False))  # exclude
            self.assertFalse(policy.allows("secrets/leak.py", count=False))  # not included
            self.assertFalse(policy.allows("keep.pem", count=False))  # ignore layer
            decision = policy.explain("src/hidden_util.py")
            self.assertEqual(decision.reason, "excluded")
            decision = policy.explain("secrets/leak.py")
            self.assertEqual(decision.reason, "not_included")

    def test_repo_scoped_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "services" / "billing-api" / "src").mkdir(parents=True)
            (ws / "services" / "billing-api" / "src" / "A.java").write_text(
                "class A {}", encoding="utf-8"
            )
            (ws / "services" / "inventory-api" / "src").mkdir(parents=True)
            (ws / "services" / "inventory-api" / "src" / "B.java").write_text(
                "class B {}", encoding="utf-8"
            )
            (ws / "docs" / "contracts").mkdir(parents=True)
            (ws / "docs" / "adrs").mkdir(parents=True)
            (ws / "docs" / "known-gaps.md").write_text("# g\n", encoding="utf-8")
            (ws / "contractmesh.yml").write_text(
                """name: mono
mode: monorepo
workspace_mapping_version: v3
repos:
  - path: .
    name: workspace
  - path: services/billing-api
    name: billing-api
  - path: services/inventory-api
    name: inventory-api
docs:
  contracts: [docs/contracts]
  adrs: [docs/adrs]
  gaps: [docs/known-gaps.md]
index:
  mode: allowlist
  include:
    - billing-api:src/**
    - docs/**
""",
                encoding="utf-8",
            )
            policy = load_index_policy(ws)
            self.assertTrue(policy.allows("services/billing-api/src/A.java", count=False))
            self.assertFalse(policy.allows("services/inventory-api/src/B.java", count=False))

    def test_collectors_respect_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            _write_basic(
                ws,
                index_block="""index:
  mode: allowlist
  include:
    - src/example.py
    - docs/contracts/**
    - docs/adrs/**
    - docs/known-gaps.md
""",
            )
            policy = load_index_policy(ws)
            docs = collect_workspace_docs(ws, policy=policy)
            rels = [rel for _p, rel in docs]
            self.assertIn("docs/contracts/example-contract.md", rels)
            anchors, _ = collect_code_anchors(
                ws,
                ["app=."],
                ws / ".contractmesh" / "index" / "chunks",
                {},
                policy=policy,
            )
            symbols = [m["symbol"] for m, _, _ in anchors if m.get("kind") == "code_anchor"]
            self.assertIn("ExampleService", symbols)
            self.assertNotIn("HiddenUtil", symbols)
            self.assertNotIn("SecretLeak", symbols)

    def test_structural_graph_respects_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            java = ws / "src" / "main" / "java" / "demo"
            java.mkdir(parents=True)
            (java / "PublicService.java").write_text(
                "package demo;\npublic class PublicService {}\n",
                encoding="utf-8",
            )
            secret = ws / "secrets"
            secret.mkdir()
            (secret / "SecretService.java").write_text(
                "package secrets;\npublic class SecretService {}\n",
                encoding="utf-8",
            )
            (ws / "docs" / "contracts").mkdir(parents=True)
            (ws / "docs" / "adrs").mkdir(parents=True)
            (ws / "docs" / "known-gaps.md").write_text("# g\n", encoding="utf-8")
            (ws / "contractmesh.yml").write_text(
                """name: sg
mode: basic
workspace_mapping_version: v3
repos:
  - path: .
    name: app
docs:
  contracts: [docs/contracts]
  adrs: [docs/adrs]
  gaps: [docs/known-gaps.md]
index:
  mode: allowlist
  include:
    - src/**
""",
                encoding="utf-8",
            )
            policy = load_index_policy(ws)
            # Force a scan; edges may be empty for a bare class, but policy must gate paths.
            self.assertTrue(policy.allows("src/main/java/demo/PublicService.java", count=False))
            self.assertFalse(policy.allows("secrets/SecretService.java", count=False))
            collect_structural_edges(ws, [("app", ".")], policy=policy)
            # secrets/ should be pruned / denied — never "allowed" under this policy.
            self.assertEqual(policy.explain("secrets/SecretService.java").reason, "not_included")

    def test_manifest_validate_and_build_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            _write_basic(
                ws,
                index_block="""index:
  mode: allowlist
  include:
    - src/example.py
    - docs/contracts/**
    - docs/adrs/**
    - docs/known-gaps.md
    - tests/**
""",
            )
            manifest = load_workspace_manifest(ws)
            self.assertEqual(validate_manifest(ws, manifest), [])
            run_build(ws)
            built = json.loads(
                (ws / ".contractmesh" / "index" / "search-index.manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            policy_stats = (built.get("build_stats") or {}).get("index_policy") or {}
            self.assertEqual(policy_stats.get("mode"), "allowlist")
            stats = policy_stats.get("stats") or {}
            self.assertGreaterEqual(int(stats.get("files_allowed", 0)), 1)
            docs = [d for d in built.get("documents", []) if d.get("kind") == "code_anchor"]
            symbols = {d.get("symbol") for d in docs}
            self.assertIn("ExampleService", symbols)
            self.assertNotIn("SecretLeak", symbols)

    def test_legacy_ignore_tests_still_hold_via_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            repo = ws / "services" / "billing-api"
            docs = repo / "docs" / "ai" / "contracts"
            docs.mkdir(parents=True)
            (ws / ".contractmeshignore").write_text("*secret*.md\n", encoding="utf-8")
            (docs / "public.md").write_text("# Public contract\n", encoding="utf-8")
            (docs / "secret-contract.md").write_text("# Secret contract\n", encoding="utf-8")
            (ws / "contractmesh.yml").write_text(
                """name: legacy
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
            self.assertNotIn(
                "services/billing-api/docs/ai/contracts/secret-contract.md", rels
            )


if __name__ == "__main__":
    unittest.main()
