#!/usr/bin/env python3
"""ContractMesh CLI — installed tool for external workspaces."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
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


def resolve_workspace_arg(args: argparse.Namespace) -> Path:
    if getattr(args, "workspace", None):
        path = Path(args.workspace).resolve()
        os.environ["CONTRACTMESH_WORKSPACE"] = str(path)
        return require_workspace(path)
    return require_workspace()


def copy_template(template: str, destination: Path, *, force: bool = False) -> None:
    src = templates_dir() / template
    if not src.is_dir():
        raise SystemExit(f"unknown template: {template}")
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        if any(part in {"__pycache__", ".git"} for part in rel.parts):
            continue
        if item.is_file() and item.suffix in {".pyc", ".pyo"}:
            continue
        target = destination / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not force:
            print(f"[skip] {target} already exists")
            continue
        shutil.copy2(item, target)
        print(f"[ok] wrote {target}")


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


def cmd_init(args: argparse.Namespace) -> int:
    if args.here or not args.path:
        destination = Path.cwd().resolve()
    else:
        destination = Path(args.path).resolve()
        if not destination.exists():
            destination.mkdir(parents=True)
    copy_template(args.template, destination, force=args.force)
    scaffold_contractmesh_dirs(destination)
    append_gitignore(destination)
    print("[ok] workspace initialized with an explicit allowlist.")
    print("Review contractmesh.yml before indexing.")
    print("Only the configured paths will be analyzed or exposed through MCP.")
    print("The starter include list is intentional — paths outside it are omitted")
    print("until you add them to index.include.")
    print("Next: edit contractmesh.yml, then run: contractmesh index && contractmesh status")
    print("Hint: contractmesh index --show-policy")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    workspace = resolve_workspace_arg(args)
    explain_path = getattr(args, "explain", None)
    if explain_path:
        from contractmesh.engine.index_policy import load_index_policy

        try:
            policy = load_index_policy(workspace)
        except ValueError as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 1
        decision = policy.explain(explain_path)
        print(json.dumps(decision.as_dict(), indent=2, ensure_ascii=False))
        return 0 if decision.allowed else 2

    if getattr(args, "show_policy", False):
        from contractmesh.engine.index_policy import load_index_policy

        try:
            policy = load_index_policy(workspace)
        except ValueError as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 1
        print(json.dumps(policy.summary(), indent=2, ensure_ascii=False))
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
    contracts = workspace / "docs" / "contracts"
    adrs = workspace / "docs" / "adrs"
    c_count = len(list(contracts.glob("**/*.md"))) if contracts.is_dir() else 0
    a_count = len(list(adrs.glob("**/*.md"))) if adrs.is_dir() else 0
    print(f"Docs:       docs/contracts/ ({c_count} files), docs/adrs/ ({a_count} files)")
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
        help="scaffold contractmesh.yml and starter docs in a project",
        description="Initialize a ContractMesh workspace from a template.",
    )
    p_init.add_argument("--here", action="store_true", help="Initialize in the current directory")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing scaffold files")
    p_init.add_argument("--template", choices=["basic", "monorepo"], default="basic")
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
