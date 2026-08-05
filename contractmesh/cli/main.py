#!/usr/bin/env python3
"""ContractMesh CLI — installed tool for external workspaces."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from contractmesh.engine.bootstrap_suggest import suggest_bootstrap, write_bootstrap_suggestions
from contractmesh.engine.export_workspace_graph import export_graph
from contractmesh.engine.workspace_manifest import load_workspace_manifest, repo_specs, validate_manifest
from contractmesh.engine.workspace_paths import (
    WORKSPACE_NOT_FOUND_MSG,
    ensure_workspace_dirs,
    require_workspace,
    workspace_layout,
)
from contractmesh.engine.workspace_search import (
    IndexNotFoundError,
    index_status,
    load_index,
    run_build,
)
from contractmesh.paths import package_root, source_checkout_root, templates_dir, tool_root


GITIGNORE_LINES = [
    ".contractmesh/index/",
    ".contractmesh/cache/",
    ".contractmesh/generated/",
    ".contractmesh/mcp/",
]

TRUST_BOOTSTRAP_NOTE = (
    "ContractMesh can suggest knowledge, but only humans can confirm it."
)

# Always copied from the template (config / ignore policy).
INIT_CONFIG_RELATIVE = (
    "contractmesh.yml",
    ".contractmeshignore",
)

# Preferred knowledge locations (first existing wins; else create the first default).
CONTRACTS_PATH_CANDIDATES = (
    "docs/contracts",
    "docs/contract",
    "contracts",
)
ADR_PATH_CANDIDATES = (
    "docs/adr",
    "docs/adrs",
    "docs/ADR",
    "adr",
    "adrs",
)
GAPS_PATH_CANDIDATES = (
    "docs/known-gaps.md",
    "docs/known_gaps.md",
    "known-gaps.md",
)

EMPTY_KNOWN_GAPS = """# Known gaps

Document confirmed risks and open enforcement gaps here.

| Gap ID | Status | Description |
| --- | --- | --- |
"""

# Markers that an existing project should not receive demo code/docs.
EXISTING_PROJECT_MARKERS = (
    ".git",
    "README.md",
    "README.rst",
    "README.txt",
    "package.json",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "composer.json",
    "Gemfile",
    "mix.exs",
    "CMakeLists.txt",
    "Makefile",
)

INIT_SKIP_SCAN_DIRS = {
    ".git",
    ".contractmesh",
    ".cursor",
    ".idea",
    ".vscode",
    ".ai",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "target",
    "coverage",
    "__pycache__",
    ".next",
    ".nuxt",
    ".turbo",
    "out",
    "tmp",
    "temp",
}

# Top-level / nested dirs worth suggesting for allowlist review (never auto-added).
INIT_SUGGEST_DIR_NAMES = {
    "src",
    "server",
    "backend",
    "frontend",
    "api",
    "app",
    "apps",
    "services",
    "packages",
    "lib",
    "cmd",
    "internal",
    "prisma",
    "scripts",
    "docker",
    "web",
    "client",
    "mobile",
    "worker",
    "workers",
    "tests",
    "test",
    "docs",
}

INIT_SUGGEST_NESTED = ("src", "resources", "lib", "app", "apps", "tests")

INIT_SUGGEST_FILES = (
    "package.json",
    "vite.config.ts",
    "vite.config.js",
    "docker-compose.yml",
    "docker-compose.prod.yml",
    "prisma/schema.prisma",
)


def resolve_workspace_arg(args: argparse.Namespace) -> Path:
    if getattr(args, "workspace", None):
        path = Path(args.workspace).resolve()
        os.environ["CONTRACTMESH_WORKSPACE"] = str(path)
        return require_workspace(path)
    return require_workspace()


def is_existing_project(destination: Path) -> bool:
    """True when the target already looks like a real project (brownfield)."""
    if not destination.is_dir():
        return False
    for name in EXISTING_PROJECT_MARKERS:
        if (destination / name).exists():
            return True
    skip_names = {".DS_Store", ".idea", ".vscode", ".contractmesh"}
    for child in destination.iterdir():
        if child.name in skip_names or child.name.startswith(".git"):
            continue
        if child.is_file():
            return True
        if child.is_dir() and any(child.iterdir()):
            return True
    return False


def inferred_workspace_name(destination: Path) -> str:
    name = destination.name.strip()
    return name or "workspace"


def _first_existing_dir(destination: Path, candidates: tuple[str, ...]) -> str | None:
    for rel in candidates:
        if (destination / rel).is_dir():
            return rel
    return None


def _first_existing_file(destination: Path, candidates: tuple[str, ...]) -> str | None:
    for rel in candidates:
        if (destination / rel).is_file():
            return rel
    return None


def resolve_knowledge_paths(destination: Path) -> dict[str, str]:
    """Pick existing brownfield knowledge paths when present; else template defaults."""
    contracts = _first_existing_dir(destination, CONTRACTS_PATH_CANDIDATES) or "docs/contracts"
    adrs = _first_existing_dir(destination, ADR_PATH_CANDIDATES) or "docs/adrs"
    gaps = _first_existing_file(destination, GAPS_PATH_CANDIDATES) or "docs/known-gaps.md"
    return {"contracts": contracts, "adrs": adrs, "gaps": gaps}


def copy_template_files(
    template: str,
    destination: Path,
    *,
    force: bool = False,
    relative_paths: list[str] | None = None,
) -> set[str]:
    """Copy selected template files, or the full tree when relative_paths is None.

    Returns the set of relative paths written (not skipped).
    """
    src = templates_dir() / template
    if not src.is_dir():
        raise SystemExit(f"unknown template: {template}")

    if relative_paths is not None:
        items: list[Path] = []
        for rel in relative_paths:
            item = src / rel
            if item.is_file():
                items.append(item)
        file_iter = items
    else:
        file_iter = [
            item
            for item in src.rglob("*")
            if item.is_file()
            and not any(part in {"__pycache__", ".git"} for part in item.relative_to(src).parts)
            and item.suffix not in {".pyc", ".pyo"}
        ]

    written: set[str] = set()
    for item in file_iter:
        rel = item.relative_to(src)
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not force:
            print(f"[skip] {target} already exists")
            continue
        shutil.copy2(item, target)
        print(f"[ok] wrote {target}")
        written.add(rel.as_posix())
    return written


def write_empty_knowledge_scaffold(
    destination: Path,
    *,
    force: bool = False,
    paths: dict[str, str] | None = None,
) -> dict[str, str]:
    resolved = paths or resolve_knowledge_paths(destination)
    for key in ("contracts", "adrs"):
        rel = resolved[key]
        path = destination / rel
        if path.is_dir():
            print(f"[ok] using existing {rel}/")
            continue
        path.mkdir(parents=True, exist_ok=True)
        keep = path / ".gitkeep"
        if not keep.is_file():
            keep.write_text("", encoding="utf-8")
            print(f"[ok] wrote {keep}")

    gaps_rel = resolved["gaps"]
    gaps = destination / gaps_rel
    if gaps.exists() and not force:
        print(f"[skip] {gaps} already exists")
        return resolved
    gaps.parent.mkdir(parents=True, exist_ok=True)
    gaps.write_text(EMPTY_KNOWN_GAPS, encoding="utf-8")
    print(f"[ok] wrote {gaps}")
    return resolved


def yaml_scalar(value: str) -> str:
    """Quote a YAML scalar when the bare form would be ambiguous or invalid."""
    text = str(value)
    if not text:
        return '""'
    needs_quotes = (
        text != text.strip()
        or text.lower() in {"true", "false", "null", "yes", "no", "on", "off"}
        or text[:1].isdigit()
        or any(ch in text for ch in ":#{}[],&*!|>%@`'\"\\")
        or "\n" in text
        or text.startswith(("-", "?", "*", "&", "!", "%", "@", "`"))
    )
    if not needs_quotes:
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def customize_init_manifest(
    destination: Path,
    *,
    knowledge: dict[str, str],
    workspace_name: str,
) -> None:
    """Rewrite placeholder identity and docs paths in a freshly written manifest."""
    path = destination / "contractmesh.yml"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    original = text
    quoted_name = yaml_scalar(workspace_name)

    # Workspace display name (template defaults).
    text = re.sub(
        r"(?m)^name:\s*(?:example-app|monorepo-workspace)\s*$",
        f"name: {quoted_name}",
        text,
        count=1,
    )
    # Prefer directory name for the primary repo label when still "app".
    text = re.sub(
        r"(?m)^(\s+name:\s+)app\s*$",
        rf"\g<1>{quoted_name}",
        text,
        count=1,
    )

    def _replace_docs_list_item(section: str, new_path: str, content: str) -> str:
        # Matches:
        #   adrs:
        #     - docs/adrs
        pattern = rf"(?m)^(\s*{re.escape(section)}:\s*\n\s*-\s+)[^\n]+"
        return re.sub(pattern, rf"\g<1>{new_path}", content, count=1)

    text = _replace_docs_list_item("contracts", knowledge["contracts"], text)
    text = _replace_docs_list_item("adrs", knowledge["adrs"], text)
    text = _replace_docs_list_item("gaps", knowledge["gaps"], text)

    if text != original:
        path.write_text(text, encoding="utf-8")
        print(f"[ok] customized {path} (name={workspace_name}, docs paths)")


def _normalize_include_root(pattern: str) -> str:
    value = pattern.strip().lstrip("./")
    if value.endswith("/**"):
        return value[:-3]
    if value.endswith("/*"):
        return value[:-2]
    return value.rstrip("/")


def include_covers_candidate(include_patterns: list[str], candidate: str) -> bool:
    """Return True when an include rule already covers the candidate path.

    Coverage is one-way: a broader include covers a narrower candidate
    (``docs/**`` covers ``docs/contracts/**``), but not the reverse.
    """
    cand = candidate.strip().lstrip("./")
    cand_root = _normalize_include_root(cand)
    for pattern in include_patterns:
        raw = str(pattern).strip().lstrip("./")
        root = _normalize_include_root(raw)
        if not root and not raw:
            continue
        if cand == raw or cand_root == root:
            return True
        # Include root is a prefix of the candidate → candidate already covered.
        if cand_root.startswith(root + "/"):
            return True
        # File candidate under a directory include.
        if not cand.endswith("/**") and (cand == root or cand.startswith(root + "/")):
            return True
    return False


def detect_candidate_includes(destination: Path) -> list[str]:
    """Heuristic paths present in the tree that operators may want to allowlist."""
    found: list[str] = []
    seen: set[str] = set()

    def add(rel: str) -> None:
        if rel not in seen:
            seen.add(rel)
            found.append(rel)

    if not destination.is_dir():
        return found

    for child in sorted(destination.iterdir(), key=lambda p: p.name.lower()):
        name = child.name
        if name in INIT_SKIP_SCAN_DIRS or name.startswith("."):
            continue
        if child.is_dir():
            if name in INIT_SUGGEST_DIR_NAMES or name.endswith("-api") or name.endswith("-web"):
                add(f"{name}/**")
            if name in {"server", "backend", "frontend", "api", "web", "client", "app", "apps"}:
                for nested in INIT_SUGGEST_NESTED:
                    if (child / nested).is_dir():
                        add(f"{name}/{nested}/**")
        elif child.is_file() and name in INIT_SUGGEST_FILES:
            add(name)

    for rel in INIT_SUGGEST_FILES:
        if "/" in rel and (destination / rel).exists():
            add(rel)

    return found


def print_allowlist_suggestions(destination: Path) -> None:
    """Surface roots outside the starter allowlist without authorizing them."""
    try:
        manifest = load_workspace_manifest(destination)
    except Exception:
        return
    include = [str(x) for x in ((manifest.get("index") or {}).get("include") or [])]
    candidates = detect_candidate_includes(destination)
    outside = [c for c in candidates if not include_covers_candidate(include, c)]
    if not outside:
        return
    print("[hint] Paths detected but not in index.include (not auto-added — review before indexing):")
    for rel in outside:
        print(f"  - {rel}")
    print("Add selected paths to contractmesh.yml → index.include, then re-run contractmesh index.")
    print("Check a path with: contractmesh index --explain PATH")


def append_gitignore(workspace: Path) -> None:
    gi = workspace / ".gitignore"
    existing = gi.read_text(encoding="utf-8") if gi.is_file() else ""
    missing = [line for line in GITIGNORE_LINES if line not in existing]
    if not missing:
        return
    block = "\n# ContractMesh generated artifacts\n" + "\n".join(missing) + "\n"
    if gi.is_file():
        gi.write_text(existing.rstrip() + "\n" + block, encoding="utf-8")
    else:
        gi.write_text(block.lstrip(), encoding="utf-8")
    print(f"[ok] updated {gi}")


def scaffold_contractmesh_dirs(workspace: Path) -> None:
    layout = ensure_workspace_dirs(workspace)
    for sub in ("index", "cache", "generated", "mcp"):
        keep = layout.workspace / ".contractmesh" / sub / ".gitkeep"
        if not keep.is_file():
            keep.write_text("", encoding="utf-8")


def adapt_monorepo_manifest_without_examples(
    destination: Path, *, workspace_name: str
) -> None:
    """Replace placeholder multi-repo paths with a valid single-root starter.

    Config-only monorepo init must not leave services/* / apps/* entries that
    do not exist on disk (check/index would fail closed).
    """
    path = destination / "contractmesh.yml"
    if not path.is_file():
        return
    quoted = yaml_scalar(workspace_name)
    path.write_text(
        f"""name: {quoted}
mode: monorepo
workspace_mapping_version: v3
repos:
  - path: .
    name: {quoted}
docs:
  contracts:
    - docs/contracts
  adrs:
    - docs/adrs
  gaps:
    - docs/known-gaps.md
lint:
  require_owner: true
  require_ids: true
  require_valid_crosslinks: true
index:
  mode: allowlist
  include:
    - docs/**
    - README.md
  # Config-only monorepo init starts with a single workspace root.
  # Add real repos and include rules after creating those directories, for example:
  #   repos:
  #     - path: services/billing-api
  #       name: billing-api
  #   index.include:
  #     - billing-api:src/**
  #     - billing-api:tests/**
  # Denylist is available only when deliberately configured.
#
# Debug: contractmesh index --explain PATH
#        contractmesh index --show-policy
""",
        encoding="utf-8",
    )
    print(
        f"[ok] adapted {path} to a single-root monorepo starter "
        "(add real service paths before indexing them)."
    )


def align_example_docs_with_knowledge(destination: Path, knowledge: dict[str, str]) -> None:
    """Move template demo docs onto resolved brownfield knowledge paths when they differ."""
    pairs = (
        ("docs/contracts/example-contract.md", f"{knowledge['contracts']}/example-contract.md"),
        ("docs/adrs/example-adr.md", f"{knowledge['adrs']}/example-adr.md"),
        ("docs/known-gaps.md", knowledge["gaps"]),
    )
    for src_rel, dst_rel in pairs:
        src = destination / src_rel
        dst = destination / dst_rel
        if not src.is_file():
            continue
        try:
            if src.resolve() == dst.resolve():
                continue
        except OSError:
            pass
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            src.unlink()
            print(f"[ok] removed template duplicate {src}")
            continue
        shutil.move(str(src), str(dst))
        print(f"[ok] placed example at {dst}")

    for maybe_empty in ("docs/adrs", "docs/contracts"):
        path = destination / maybe_empty
        if not path.is_dir():
            continue
        try:
            remaining = [p for p in path.iterdir() if p.name != ".gitkeep"]
        except OSError:
            continue
        if remaining:
            continue
        keep = path / ".gitkeep"
        if keep.is_file():
            keep.unlink()
        try:
            path.rmdir()
            print(f"[ok] removed unused template dir {path}")
        except OSError:
            pass


def cmd_init(args: argparse.Namespace) -> int:
    if args.here or not args.path:
        destination = Path.cwd().resolve()
    else:
        destination = Path(args.path).resolve()
        if not destination.exists():
            destination.mkdir(parents=True)

    with_examples = bool(getattr(args, "with_examples", False))
    existing = is_existing_project(destination)
    workspace_name = inferred_workspace_name(destination)
    knowledge = resolve_knowledge_paths(destination)

    # Brownfield never gets demo code/docs unless the user opts in explicitly.
    # Greenfield defaults are also non-invasive (facts first); examples need --with-examples.
    wrote: set[str] = set()
    if with_examples:
        if existing:
            print(
                "[warn] existing project detected; writing template examples because "
                "--with-examples was set."
            )
        wrote = copy_template_files(args.template, destination, force=args.force)
        align_example_docs_with_knowledge(destination, knowledge)
    else:
        if existing:
            print(
                "[ok] existing project detected — initializing without example code, "
                "tests, or demo contracts (facts first)."
            )
            print("Hint: pass --with-examples only when you intentionally want the scaffold demo.")
        wrote = copy_template_files(
            args.template,
            destination,
            force=args.force,
            relative_paths=list(INIT_CONFIG_RELATIVE),
        )
        if args.template == "monorepo" and "contractmesh.yml" in wrote:
            adapt_monorepo_manifest_without_examples(
                destination, workspace_name=workspace_name
            )
            print(
                "[hint] monorepo without --with-examples uses a single workspace root; "
                "add real services to contractmesh.yml after they exist on disk."
            )
        knowledge = write_empty_knowledge_scaffold(
            destination, force=args.force, paths=knowledge
        )

    if "contractmesh.yml" in wrote:
        customize_init_manifest(
            destination, knowledge=knowledge, workspace_name=workspace_name
        )

    scaffold_contractmesh_dirs(destination)
    append_gitignore(destination)
    print("[ok] workspace initialized with an explicit allowlist.")
    print("Review contractmesh.yml before indexing.")
    print("Only the configured paths will be analyzed or exposed through MCP.")
    print("The starter include list is intentional — paths outside it are omitted")
    print("until you add them to index.include.")
    print_allowlist_suggestions(destination)
    print("Next: edit contractmesh.yml, then run: contractmesh index && contractmesh status")
    print("Hint: contractmesh index --show-policy")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    workspace = resolve_workspace_arg(args)
    explain_path = getattr(args, "explain", None)
    if explain_path:
        from contractmesh.engine.index_explain import explain_index_path

        try:
            payload = explain_index_path(workspace, explain_path)
        except ValueError as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 1
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if payload.get("allowed") else 2

    if getattr(args, "show_policy", False):
        from contractmesh.engine.index_policy import load_index_policy

        try:
            policy = load_index_policy(workspace)
        except ValueError as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 1
        print(json.dumps(policy.summary(evaluated=False), indent=2, ensure_ascii=False))
        return 0

    # Fail closed before walking the tree when allowlist is misconfigured.
    from contractmesh.engine.workspace_manifest import load_workspace_manifest, validate_manifest

    try:
        manifest = load_workspace_manifest(workspace)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    errors = validate_manifest(workspace, manifest)
    if errors:
        for err in errors:
            print(f"[FAIL] {err}", file=sys.stderr)
        return 1

    run_build(workspace)
    print("[ok] index built")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    workspace = resolve_workspace_arg(args)
    layout = workspace_layout(workspace)
    yml = workspace / "contractmesh.yml"
    print(f"Workspace:  {workspace}")
    print(f"Config:     {'contractmesh.yml found' if yml.is_file() else 'missing'}")
    try:
        from contractmesh.engine.index_policy import load_index_policy

        policy = load_index_policy(workspace)
        include_n = len(policy.include)
        print(
            f"Policy:     mode={policy.mode}, include={include_n} rule(s) "
            "(contractmesh index --show-policy)"
        )
    except ValueError as exc:
        print(f"Policy:     invalid ({exc})")
    if layout.manifest_path.is_file():
        st = index_status(workspace, deep=False)
        age = st.get("generated_at_age_hours")
        age_s = f", {age:.1f}h ago" if isinstance(age, (int, float)) else ""
        print(
            f"Index:      {layout.manifest_path.relative_to(workspace)} "
            f"({st.get('total_docs', 0)} docs{age_s})"
        )
    else:
        print("Index:      missing (run: contractmesh index)")
    try:
        manifest = load_workspace_manifest(workspace)
        docs_cfg = manifest.get("docs") or {}
        contract_roots = [str(p) for p in (docs_cfg.get("contracts") or ["docs/contracts"])]
        adr_roots = [str(p) for p in (docs_cfg.get("adrs") or ["docs/adrs"])]
    except Exception:
        contract_roots = ["docs/contracts"]
        adr_roots = ["docs/adrs"]

    def _md_count(roots: list[str]) -> tuple[str, int]:
        total = 0
        labels: list[str] = []
        for rel in roots:
            path = workspace / rel
            labels.append(f"{rel}/")
            if path.is_dir():
                total += len(list(path.glob("**/*.md")))
            elif path.is_file() and path.suffix == ".md":
                total += 1
        return ", ".join(labels), total

    c_label, c_count = _md_count(contract_roots)
    a_label, a_count = _md_count(adr_roots)
    print(f"Docs:       {c_label} ({c_count} files), {a_label} ({a_count} files)")
    code = list(workspace.glob("src/**/*.py")) + list(workspace.glob("src/**/*.java"))
    tests = list(workspace.glob("tests/**/*.py")) + list(workspace.glob("tests/**/*.java"))
    if code:
        print(f"Code:       {code[0].relative_to(workspace)}")
    if tests:
        print(f"Tests:      {tests[0].relative_to(workspace)}")
    mcp_cfg = layout.mcp_dir / "cursor.json"
    print(f"MCP:        {'ready' if mcp_cfg.is_file() else 'not configured'} ({mcp_cfg.relative_to(workspace)})")
    return 0


def _validate_workspace_docs(workspace: Path) -> list[str]:
    errors: list[str] = []
    try:
        manifest = load_workspace_manifest(workspace)
    except FileNotFoundError as exc:
        return [str(exc)]
    errors.extend(validate_manifest(workspace, manifest))
    layout = workspace_layout(workspace)
    if not layout.manifest_path.is_file():
        errors.append("index missing; run: contractmesh index")
    return errors


def cmd_check(args: argparse.Namespace) -> int:
    if args.release:
        return cmd_check_release(args)
    workspace = resolve_workspace_arg(args)
    errors = _validate_workspace_docs(workspace)
    if errors:
        for err in errors:
            print(f"[FAIL] {err}")
        return 1
    print("[ok] workspace check passed")
    return 0


def cmd_check_release(_args: argparse.Namespace) -> int:
    checkout = source_checkout_root()
    if checkout is None:
        print(
            "[FAIL] `contractmesh check --release` is only available in the "
            "ContractMesh source repository (maintainer/CI).\n"
            "  Installed wheel: run `contractmesh self check` to validate installation.\n"
            "  Project workspace: run `contractmesh check` in your project directory.",
            file=sys.stderr,
        )
        return 1
    fixture = checkout / "tests" / "fixtures" / "basic-workspace"
    if not fixture.is_dir():
        print(f"[FAIL] fixture missing: {fixture}", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="contractmesh-release-") as tmp:
        ws = Path(tmp)
        shutil.copytree(fixture, ws, dirs_exist_ok=True)
        os.environ["CONTRACTMESH_WORKSPACE"] = str(ws)
        run_build(ws)
        try:
            load_index(ws)
        except IndexNotFoundError as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 1
        tests = [
            f"scripts.lib.{path.stem}"
            for path in sorted((checkout / "scripts" / "lib").glob("test_*.py"))
            if path.name != "test_cli.py"
        ]
        result = subprocess.run(
            [sys.executable, "-m", "unittest", *tests],
            cwd=checkout,
            env={
                **os.environ,
                "CONTRACTMESH_WORKSPACE": str(ws),
                "CONTRACTMESH_SKIP_RELEASE_RECURSION": "1",
            },
        )
        if result.returncode != 0:
            return result.returncode
    print("[ok] release check passed")
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    workspace = resolve_workspace_arg(args)
    graph = export_graph(workspace)
    if args.output:
        out = Path(args.output)
        out.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"[ok] wrote {out}")
    else:
        print(json.dumps(graph, indent=2, ensure_ascii=False))
    return 0


def cmd_mcp(_args: argparse.Namespace) -> int:
    workspace = resolve_workspace_arg(_args)
    os.environ["CONTRACTMESH_WORKSPACE"] = str(workspace)
    from contractmesh.mcp.server import main as mcp_main

    mcp_main()
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    print("== ContractMesh doctor ==")
    print(f"python: {sys.version.split()[0]}")
    print(f"tool: {tool_root()}")
    try:
        workspace = resolve_workspace_arg(args)
        print(f"workspace: {workspace}")
        errors = _validate_workspace_docs(workspace)
        for err in errors:
            print(f"[WARN] {err}")
    except FileNotFoundError:
        print(f"workspace: not found ({WORKSPACE_NOT_FOUND_MSG})")
    mcp_dep = importlib.util.find_spec("mcp")
    print(f"mcp package: {'installed' if mcp_dep else 'missing (pip install contractmesh[mcp])'}")
    return 0


def cmd_docs_impact(args: argparse.Namespace) -> int:
    """Analyze documentation impact for a git diff or worktree changes."""
    from contractmesh.engine.documentation_impact import (
        DEPRECATION_DOCS_DRIFT_CHECK,
        STATE_NONE,
        format_documentation_impact,
    )
    from contractmesh.engine.git_workspace_tools import documentation_impact

    if getattr(args, "deprecated_alias", False):
        print(
            f"warning: `{DEPRECATION_DOCS_DRIFT_CHECK['message']}` "
            f"(replacement: {DEPRECATION_DOCS_DRIFT_CHECK['replacement_cli']})",
            file=sys.stderr,
        )

    workspace = resolve_workspace_arg(args)
    try:
        manifest, _ = load_index(workspace)
    except IndexNotFoundError:
        print("search index missing — run: contractmesh index", file=sys.stderr)
        return 1

    base = getattr(args, "diff", None)
    include_worktree = base is None
    head = "HEAD"
    if base and "..." in base:
        left, right = base.split("...", 1)
        base, head = left.strip() or None, right.strip() or "HEAD"
        include_worktree = False
    elif base:
        include_worktree = False

    result, err = documentation_impact(
        workspace,
        manifest,
        base=base,
        head=head,
        include_worktree=include_worktree,
    )
    if err:
        print(err, file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if result.get("state") == STATE_NONE:
        # Silence when no impact — success exit.
        return 0

    text = format_documentation_impact(result)
    if text:
        print(text, end="")
    return 0


def cmd_bootstrap(args: argparse.Namespace) -> int:
    if not args.suggest:
        print("Usage: contractmesh bootstrap --suggest [--repo NAME] [--index] [--dry-run]")
        return 2
    workspace = resolve_workspace_arg(args)
    if args.index:
        run_build(workspace)
    try:
        manifest, _ = load_index(workspace)
    except IndexNotFoundError:
        run_build(workspace)
        manifest, _ = load_index(workspace)
    payload = suggest_bootstrap(workspace, manifest, repo_filter=args.repo)
    out = write_bootstrap_suggestions(workspace, payload)
    print(f"[ok] Draft suggestions written to {out.relative_to(workspace)}")
    print(TRUST_BOOTSTRAP_NOTE)
    print("Review before copying anything into docs/contracts/.")
    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_self_check(_args: argparse.Namespace) -> int:
    print("== ContractMesh self check ==")
    print(f"package: {package_root()}")
    checkout = source_checkout_root()
    if checkout is not None:
        print(f"source checkout: {checkout}")
    else:
        print("source checkout: (not detected — installed wheel)")
    ok = True
    checks = (
        ("engine.build_search_index", package_root() / "engine" / "build_search_index.py"),
        ("mcp.server", package_root() / "mcp" / "server.py"),
        ("templates/basic", templates_dir() / "basic"),
    )
    for label, path in checks:
        status = "ok" if path.exists() else "missing"
        print(f"  {label}: {status}")
        ok = ok and path.exists()
    if importlib.util.find_spec("mcp") is None:
        print("  mcp dependency: missing (pip install contractmesh[mcp])")
        ok = False
    else:
        print("  mcp dependency: ok")
    return 0 if ok else 1


def cmd_self_upgrade(_args: argparse.Namespace) -> int:
    print("Upgrade ContractMesh with your package manager, for example:")
    print("  pipx upgrade contractmesh")
    print("  pip install -U contractmesh")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contractmesh",
        description=(
            "Local engineering knowledge layer for AI coding agents. "
            "Run inside your project after init — not inside this tool repository."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Quick start:\n"
            "  contractmesh init --here\n"
            "  contractmesh index\n"
            "  contractmesh mcp"
        ),
    )
    parser.add_argument(
        "--workspace",
        help="path to a workspace with contractmesh.yml (default: walk up from cwd)",
    )
    sub = parser.add_subparsers(
        dest="command",
        required=True,
        title="commands",
        metavar="COMMAND",
        help="run contractmesh COMMAND --help for details",
    )

    p_init = sub.add_parser(
        "init",
        help="scaffold contractmesh.yml in a project (non-invasive by default)",
        description=(
            "Initialize a ContractMesh workspace. By default only writes config, "
            "ignore files, empty knowledge directories, and .gitignore updates — "
            "no example code, tests, or demo contracts. Pass --with-examples for "
            "the full scaffold demo."
        ),
    )
    p_init.add_argument("--here", action="store_true", help="Initialize in the current directory")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing scaffold files")
    p_init.add_argument("--template", choices=["basic", "monorepo"], default="basic")
    p_init.add_argument(
        "--with-examples",
        action="store_true",
        help=(
            "Copy template example code, tests, and demo contracts/ADRs. "
            "Required for demo content; never the default in existing projects."
        ),
    )
    p_init.add_argument("path", nargs="?", help="Target directory (created if missing)")
    p_init.set_defaults(func=cmd_init)

    sub.add_parser(
        "status",
        help="show workspace health, index age, and doc summary",
        description="Print a concise status report for the current workspace.",
    ).set_defaults(func=cmd_status)
    p_index = sub.add_parser(
        "index",
        help="build or rebuild the local search index",
        description=(
            "Index contracts, ADRs, gaps, and code anchors under .contractmesh/index/. "
            "Use --explain PATH to show why a path is included or excluded by the "
            "index security policy (allowlist/denylist/ignore)."
        ),
    )
    p_index.add_argument(
        "--explain",
        metavar="PATH",
        help="explain index policy decision for a workspace-relative path (no rebuild)",
    )
    p_index.add_argument(
        "--show-policy",
        action="store_true",
        help="print the active index security policy as JSON (no rebuild)",
    )
    p_index.set_defaults(func=cmd_index)

    p_check = sub.add_parser(
        "check",
        help="validate workspace configuration and index",
        description=(
            "Validate the current workspace manifest and index. "
            "Maintainers in the source repository can pass --release for the full CI gate."
        ),
    )
    p_check.add_argument(
        "--release",
        action="store_true",
        help="Maintainer/CI only: full release gate (requires source checkout)",
    )
    p_check.set_defaults(func=cmd_check)

    p_graph = sub.add_parser(
        "graph",
        help="export the knowledge graph as JSON",
        description="Export contracts, anchors, and crosslinks as deterministic JSON.",
    )
    p_graph.add_argument("--output", "-o")
    p_graph.set_defaults(func=cmd_graph)

    sub.add_parser(
        "mcp",
        help="start the local MCP server for AI clients",
        description="Run the workspace-knowledge MCP server over stdio.",
    ).set_defaults(func=cmd_mcp)
    sub.add_parser(
        "doctor",
        help="diagnose tool install and workspace setup",
        description="Check tool paths, optional MCP venv, and workspace doctor hints.",
    ).set_defaults(func=cmd_doctor)

    p_bootstrap = sub.add_parser(
        "bootstrap",
        help="suggest draft contracts, ADRs, and gaps",
        description="Draft-only suggestions under .contractmesh/generated/ (never auto-confirms).",
    )
    p_bootstrap.add_argument("--suggest", action="store_true")
    p_bootstrap.add_argument("--repo")
    p_bootstrap.add_argument("--dry-run", action="store_true")
    p_bootstrap.add_argument("--index", action="store_true")
    p_bootstrap.set_defaults(func=cmd_bootstrap)

    p_docs = sub.add_parser(
        "docs",
        help="documentation impact and review helpers",
        description="Evidence-based documentation review targets (not generic reminders).",
    )
    docs_sub = p_docs.add_subparsers(dest="docs_command", required=True)
    p_docs_impact = docs_sub.add_parser(
        "impact",
        help="analyze documentation impact for a diff or worktree",
        description=(
            "Resolve linked contracts/ADRs/gaps for changed symbols and emit docs_to_review. "
            "Prints nothing when state is none."
        ),
    )
    p_docs_impact.add_argument(
        "--diff",
        metavar="RANGE",
        help="git range like main...HEAD (default: current worktree changes)",
    )
    p_docs_impact.add_argument("--json", action="store_true", help="print full payload as JSON")
    p_docs_impact.set_defaults(func=cmd_docs_impact, deprecated_alias=False)

    p_docs_drift = docs_sub.add_parser(
        "drift",
        help="deprecated alias of docs impact",
        description="Deprecated alias of `docs impact`. Prefer `contractmesh docs impact`.",
    )
    p_docs_drift.add_argument("--diff", metavar="RANGE", help="git range like main...HEAD")
    p_docs_drift.add_argument("--json", action="store_true", help="print full payload as JSON")
    p_docs_drift.set_defaults(func=cmd_docs_impact, deprecated_alias=True)

    p_self = sub.add_parser(
        "self",
        help="verify installation or show upgrade instructions",
        description="Tool-level commands that do not require a workspace.",
    )
    self_sub = p_self.add_subparsers(dest="self_command", required=True)
    self_sub.add_parser("check", help="verify templates, engine, and MCP extra").set_defaults(func=cmd_self_check)
    self_sub.add_parser("upgrade", help="Show upgrade instructions").set_defaults(func=cmd_self_upgrade)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "self":
        return int(args.func(args) or 0)
    if args.command != "init" and args.command != "self":
        try:
            if args.command in {"check"} and args.release:
                pass
            elif args.command not in {"doctor"}:
                resolve_workspace_arg(args)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
