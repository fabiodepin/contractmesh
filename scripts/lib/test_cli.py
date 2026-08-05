#!/usr/bin/env python3
"""Tests for the ContractMesh CLI."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from contractmesh.paths import repo_root
ROOT = repo_root()


def cli(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    if env is not None:
        run_env = dict(env)
    else:
        run_env = dict(os.environ)
    run_env["PYTHONPATH"] = f"{ROOT}{os.pathsep}{run_env.get('PYTHONPATH', '')}"
    return subprocess.run(
        [sys.executable, "-m", "contractmesh.cli.main", *args],
        cwd=cwd or ROOT,
        env=run_env,
        text=True,
        capture_output=True,
        check=False,
    )


class TestContractMeshCli(unittest.TestCase):
    def test_help(self) -> None:
        result = cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("contractmesh", result.stdout)

    def test_self_check(self) -> None:
        result = cli("self", "check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("package:", result.stdout)

    def test_init_basic_default_is_non_invasive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = cli("init", "--here", "--template", "basic", cwd=Path(tmp))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("explicit allowlist", result.stdout)
            self.assertIn("Only the configured paths", result.stdout)
            ws = Path(tmp)
            self.assertTrue((ws / "contractmesh.yml").is_file())
            self.assertTrue((ws / ".contractmeshignore").is_file())
            self.assertTrue((ws / "docs" / "contracts" / ".gitkeep").is_file())
            self.assertTrue((ws / "docs" / "adrs" / ".gitkeep").is_file())
            self.assertTrue((ws / "docs" / "known-gaps.md").is_file())
            manifest_text = (ws / "contractmesh.yml").read_text(encoding="utf-8")
            self.assertIn(f"name: {ws.name}", manifest_text)
            self.assertNotIn("name: example-app", manifest_text)
            self.assertFalse((ws / "src" / "example.py").exists())
            self.assertFalse((ws / "tests" / "test_example.py").exists())
            self.assertFalse((ws / "docs" / "contracts" / "example-contract.md").exists())
            self.assertFalse((ws / "docs" / "adrs" / "example-adr.md").exists())
            gaps = (ws / "docs" / "known-gaps.md").read_text(encoding="utf-8")
            self.assertNotIn("APP-KG-001", gaps)
            self.assertTrue((ws / ".contractmesh" / "index").is_dir())

    def test_init_with_examples_copies_scaffold_demo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = cli(
                "init", "--here", "--template", "basic", "--with-examples", cwd=Path(tmp)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            ws = Path(tmp)
            self.assertTrue((ws / "src" / "example.py").is_file())
            self.assertTrue((ws / "tests" / "test_example.py").is_file())
            self.assertTrue((ws / "docs" / "contracts" / "example-contract.md").is_file())
            self.assertTrue((ws / "docs" / "adrs" / "example-adr.md").is_file())
            self.assertIn(f"name: {ws.name}", (ws / "contractmesh.yml").read_text(encoding="utf-8"))

    def test_init_existing_project_skips_examples_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "README.md").write_text("# real project\n", encoding="utf-8")
            (ws / "src").mkdir()
            (ws / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
            result = cli("init", "--here", cwd=ws)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("existing project detected", result.stdout)
            self.assertTrue((ws / "contractmesh.yml").is_file())
            self.assertFalse((ws / "src" / "example.py").exists())
            self.assertFalse((ws / "tests" / "test_example.py").exists())
            self.assertFalse((ws / "docs" / "contracts" / "example-contract.md").exists())
            self.assertTrue((ws / "src" / "app.py").is_file())
            self.assertEqual((ws / "README.md").read_text(encoding="utf-8"), "# real project\n")

    def test_init_reuses_existing_docs_adr_and_suggests_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "app-vulnerabilities"
            root.mkdir()
            (root / "README.md").write_text("# app\n", encoding="utf-8")
            (root / "docs" / "adr").mkdir(parents=True)
            (root / "docs" / "adr" / "0001.md").write_text("# ADR\n", encoding="utf-8")
            (root / "server" / "src").mkdir(parents=True)
            (root / "server" / "src" / "index.ts").write_text("export {}\n", encoding="utf-8")
            (root / "prisma").mkdir()
            (root / "prisma" / "schema.prisma").write_text("datasource db {}\n", encoding="utf-8")
            (root / "package.json").write_text("{}\n", encoding="utf-8")
            result = cli("init", "--here", cwd=root)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("using existing docs/adr/", result.stdout)
            self.assertFalse((root / "docs" / "adrs").exists())
            yml = (root / "contractmesh.yml").read_text(encoding="utf-8")
            self.assertIn("name: app-vulnerabilities", yml)
            self.assertIn("- docs/adr", yml)
            self.assertNotIn("- docs/adrs", yml)
            self.assertIn("not in index.include", result.stdout)
            self.assertIn("server/**", result.stdout)
            self.assertIn("server/src/**", result.stdout)
            self.assertIn("prisma/**", result.stdout)
    def test_init_no_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            first = cli("init", "--here", "--template", "basic", "--with-examples", cwd=ws)
            self.assertEqual(first.returncode, 0, first.stderr)
            before = (ws / "contractmesh.yml").read_text(encoding="utf-8")
            second = cli("init", "--here", "--template", "basic", "--with-examples", cwd=ws)
            self.assertEqual(second.returncode, 0, second.stderr)
            after = (ws / "contractmesh.yml").read_text(encoding="utf-8")
            self.assertEqual(before, after)
            self.assertIn("[skip]", second.stdout)

    def test_commands_fail_without_init(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            env = {
                **{k: v for k, v in os.environ.items() if k not in ("CONTRACTMESH_WORKSPACE", "WORKSPACE_ROOT")},
                "PYTHONPATH": f"{ROOT}{os.pathsep}",
            }
            result = cli("status", cwd=Path(tmp), env=env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("contractmesh init --here", result.stderr)

    def test_status_after_init_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            self.assertEqual(
                cli("init", "--here", "--template", "basic", "--with-examples", cwd=ws).returncode,
                0,
            )
            self.assertEqual(cli("index", cwd=ws).returncode, 0)
            result = cli("status", cwd=ws)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Workspace:", result.stdout)
            self.assertIn(".contractmesh/index", result.stdout)

    def test_index_explain_and_show_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            self.assertEqual(
                cli("init", "--here", "--template", "basic", "--with-examples", cwd=ws).returncode,
                0,
            )
            policy = cli("index", "--show-policy", cwd=ws)
            self.assertEqual(policy.returncode, 0, policy.stderr)
            self.assertIn('"mode": "allowlist"', policy.stdout)
            explained = cli("index", "--explain", "src/example.py", cwd=ws)
            self.assertEqual(explained.returncode, 0, explained.stderr)
            self.assertIn('"allowed": true', explained.stdout)

    def test_init_templates_use_allowlist_never_denylist(self) -> None:
        from contractmesh.engine.workspace_manifest import load_workspace_manifest

        for template in ("basic", "monorepo"):
            with self.subTest(template=template):
                with tempfile.TemporaryDirectory() as tmp:
                    ws = Path(tmp)
                    result = cli("init", "--here", "--template", template, cwd=ws)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    manifest = load_workspace_manifest(ws)
                    self.assertEqual((manifest.get("index") or {}).get("mode"), "allowlist")
                    include = (manifest.get("index") or {}).get("include") or []
                    self.assertTrue(include, "init must emit a non-empty allowlist include")
                    policy = cli("index", "--show-policy", cwd=ws)
                    self.assertEqual(policy.returncode, 0, policy.stderr)
                    self.assertIn('"mode": "allowlist"', policy.stdout)
                    self.assertNotIn('"mode": "denylist"', policy.stdout)

    def test_check_release(self) -> None:
        if os.environ.get("CONTRACTMESH_SKIP_RELEASE_RECURSION"):
            self.skipTest("nested release check")
        result = cli("check", "--release")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
