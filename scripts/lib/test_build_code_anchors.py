#!/usr/bin/env python3
"""Tests for build_code_anchors."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from contractmesh.engine.build_code_anchors import (
    anchor_id_for,
    anchor_sort_key,
    collect_code_anchors,
    collect_ts_sources,
    collect_vue_sources,
    extract_java_classes,
    extract_yaml_blocks,
    index_java_file,
    index_vue_file,
    resolve_cap_per_repo,
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


class TestCollectTsSources(unittest.TestCase):
    def test_discovers_nested_server_src_curated_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "server" / "src").mkdir(parents=True)
            (ws / "server" / "src" / "AuthService.ts").write_text(
                "export class AuthService {}\n", encoding="utf-8"
            )
            (ws / "server" / "src" / "index.ts").write_text("export {}\n", encoding="utf-8")
            found = {p.name for p in collect_ts_sources(ws, ".")}
            self.assertIn("AuthService.ts", found)
            self.assertNotIn("index.ts", found)


class TestVueAndCap(unittest.TestCase):
    def test_resolve_cap_accepts_string_from_yaml_subset(self) -> None:
        self.assertEqual(resolve_cap_per_repo("850"), 850)
        self.assertEqual(resolve_cap_per_repo(850), 850)
        self.assertEqual(resolve_cap_per_repo(None), 500)

    def test_collect_vue_curated_paths_and_pascal_stem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            repo = "demo-view"
            view = ws / repo / "src" / "views" / "TicketsView.vue"
            view.parent.mkdir(parents=True)
            view.write_text("<template><div /></template>\n", encoding="utf-8")
            kebab = ws / repo / "src" / "views" / "tickets-view.vue"
            kebab.write_text("<template><div /></template>\n", encoding="utf-8")
            other = ws / repo / "src" / "components" / "Misc.vue"
            other.parent.mkdir(parents=True)
            other.write_text("<template><div /></template>\n", encoding="utf-8")
            found = {p.name for p in collect_vue_sources(ws, repo)}
            self.assertIn("TicketsView.vue", found)
            self.assertIn("tickets-view.vue", found)
            self.assertNotIn("Misc.vue", found)
            chunks = ws / ".contractmesh" / "index" / "chunks"
            entries = index_vue_file(
                ws, view, view.relative_to(ws).as_posix(), repo, chunks, {}, 58
            )
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0][0]["anchor_type"], "vue_component")
            skipped = index_vue_file(
                ws, kebab, kebab.relative_to(ws).as_posix(), repo, chunks, {}, 58
            )
            self.assertEqual(skipped, [])

    def test_truncate_keeps_higher_priority_anchor_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "contractmesh.yml").write_text(
                "name: demo\nmode: default\nrepos:\n"
                "  - path: demo-api\n    name: demo-api\n"
                "index:\n  mode: allowlist\n  include:\n    - demo-api:src/**\n",
                encoding="utf-8",
            )
            java_root = ws / "demo-api" / "src" / "main" / "java" / "demo"
            java_root.mkdir(parents=True)
            (java_root / "controllers").mkdir()
            (java_root / "controllers" / "DemoController.java").write_text(
                "public class DemoController {}\n", encoding="utf-8"
            )
            (java_root / "entity").mkdir()
            for i in range(5):
                (java_root / "entity" / f"Thing{i}.java").write_text(
                    f"public class Thing{i} {{}}\n", encoding="utf-8"
                )
            chunks = ws / ".contractmesh" / "index" / "chunks"
            entries, counts, truncated = collect_code_anchors(
                ws,
                ["demo-api=demo-api"],
                chunks,
                {},
                cap_per_repo=2,
            )
            self.assertEqual(counts["demo-api"], 2)
            self.assertIn("demo-api", truncated)
            types = [m["anchor_type"] for m, _, _ in entries]
            self.assertIn("controller", types)
            self.assertEqual(anchor_sort_key(entries[0])[0], 0)


if __name__ == "__main__":
    unittest.main()
