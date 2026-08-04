#!/usr/bin/env python3
"""Strict ContractMesh document validation for docs-lint."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from .build_code_anchors import (
    extract_java_classes,
    TS_EXPORT_CLASS_RE,
    TS_EXPORT_CONST_RE,
    GO_FUNC_RE,
)
from .build_search_index import is_known_gap_id, parse_front_matter
from .index_policy import load_index_policy
from .workspace_manifest import load_workspace_manifest, validate_manifest

VALID_ADR_STATUSES = {"proposed", "accepted", "superseded", "deprecated", "rejected"}
GAP_ID_RE = re.compile(r"\b[A-Z]{2,5}(?:-[A-Z0-9]+){1,5}-[0-9]{2,}\b")


def repo_docs(workspace: Path, repo_path: str, rel_dirs: list[str]) -> list[Path]:
    policy = load_index_policy(workspace)
    files: list[Path] = []
    for rel_dir in rel_dirs:
        base = workspace / repo_path / rel_dir
        if not base.is_dir():
            continue
        files.extend(
            sorted(
                p
                for p in base.rglob("*.md")
                if p.is_file() and not policy.ignores(p, count=False)
            )
        )
    return files


def repo_file(workspace: Path, repo_path: str, rel_path: str) -> Path:
    return workspace / repo_path / rel_path


def collect_anchor_symbols(workspace: Path, repo_path: str) -> set[str]:
    policy = load_index_policy(workspace)
    symbols: set[str] = set()
    base = workspace / repo_path

    def visible(path: Path) -> bool:
        return path.is_file() and not policy.ignores(path, count=False)

    for path in list((base / "src" / "main" / "java").rglob("*.java")) if (base / "src" / "main" / "java").is_dir() else []:
        if not visible(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        symbols.update(name for name, _ in extract_java_classes(text))
    for path in list((base / "src").rglob("*.ts")) if (base / "src").is_dir() else []:
        if "node_modules" in path.parts or path.name.endswith((".test.ts", ".spec.ts")):
            continue
        if not visible(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        symbols.update(m.group(1) for m in TS_EXPORT_CLASS_RE.finditer(text))
        symbols.update(m.group(1) for m in TS_EXPORT_CONST_RE.finditer(text))
        if not symbols and path.stem.endswith("Service"):
            symbols.add(path.stem)
    for root_name in ("internal", "cmd"):
        root = base / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.go"):
            if path.name.endswith("_test.go"):
                continue
            if not visible(path):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            symbols.update(m.group(1) for m in GO_FUNC_RE.finditer(text))
    return symbols


def normalize_anchor(value: str) -> str:
    return value.strip().split(".", 1)[0]


def fail(errors: list[str], path: Path, field: str, value: object, message: str) -> None:
    errors.append(f"{path}: {field}={value!r}: {message}")


def main(argv: list[str]) -> int:
    workspace = Path(argv[1] if len(argv) > 1 else ".").resolve()
    manifest = load_workspace_manifest(workspace)
    errors = validate_manifest(workspace, manifest)
    lint = manifest.get("lint") or {}
    docs_cfg = manifest.get("docs") or {}
    contract_dirs = list(docs_cfg.get("contracts") or ["docs/ai/contracts"])
    adr_dirs = list(docs_cfg.get("adrs") or ["docs/adrs"])
    gap_paths = list(docs_cfg.get("gaps") or ["docs/ai/known-gaps.md"])

    external_ids: dict[str, Path] = {}
    related_contract_refs: list[tuple[Path, str]] = []
    related_anchor_refs: list[tuple[Path, str, str]] = []
    all_anchor_symbols: dict[str, set[str]] = {}
    gap_ids: dict[str, Path] = {}

    for repo in manifest.get("repos", []):
        repo_path = repo["path"]
        repo_name = repo["name"]
        all_anchor_symbols[repo_name] = collect_anchor_symbols(workspace, repo_path)

        docs: list[tuple[str, Path]] = []
        for path in repo_docs(workspace, repo_path, contract_dirs):
            if path.name.lower() != "readme.md":
                docs.append(("contract", path))
        for path in repo_docs(workspace, repo_path, adr_dirs):
            docs.append(("adr", path))

        for kind, path in docs:
            raw = path.read_text(encoding="utf-8", errors="replace")
            meta, body = parse_front_matter(raw)
            doc_id = str(meta.get("id", "")).strip()
            if lint.get("require_ids") and not doc_id:
                fail(errors, path, "id", doc_id, f"{kind} requires front matter id")
            if doc_id:
                if doc_id in external_ids:
                    fail(errors, path, "id", doc_id, f"duplicate id already used by {external_ids[doc_id]}")
                external_ids[doc_id] = path

            owner = meta.get("owner")
            if lint.get("require_owner") and not isinstance(owner, dict):
                fail(errors, path, "owner", owner, f"{kind} requires owner block")
            if isinstance(owner, dict):
                if lint.get("require_owner") and not owner.get("team"):
                    fail(errors, path, "owner.team", owner.get("team"), "owner.team is required")
                if lint.get("require_owner") and not owner.get("service"):
                    fail(errors, path, "owner.service", owner.get("service"), "owner.service is required")

            status = str(meta.get("status", "")).strip().lower()
            if kind == "adr" and status and status not in VALID_ADR_STATUSES:
                fail(errors, path, "status", status, f"ADR status must be one of {sorted(VALID_ADR_STATUSES)}")
            if kind == "adr" and not status:
                fail(errors, path, "status", status, "ADR status is required")

            for ref in meta.get("related_contracts") or []:
                related_contract_refs.append((path, str(ref)))
            for ref in meta.get("related_anchors") or []:
                related_anchor_refs.append((path, repo_name, str(ref)))

        for gap_rel in gap_paths:
            gap_file = repo_file(workspace, repo_path, gap_rel)
            if not gap_file.is_file():
                continue
            for gap in GAP_ID_RE.findall(gap_file.read_text(encoding="utf-8", errors="replace")):
                if not is_known_gap_id(gap):
                    continue
                if gap in gap_ids:
                    fail(errors, gap_file, "gap_id", gap, f"duplicate gap id already used by {gap_ids[gap]}")
                gap_ids[gap] = gap_file

    for external_id, path in external_ids.items():
        if external_id in gap_ids:
            fail(errors, path, "id", external_id, f"duplicates gap id from {gap_ids[external_id]}")

    if lint.get("require_valid_crosslinks"):
        for path, ref in related_contract_refs:
            if ref not in external_ids:
                fail(errors, path, "related_contracts", ref, "target id not found")
        global_symbols = set().union(*all_anchor_symbols.values()) if all_anchor_symbols else set()
        for path, repo_name, ref in related_anchor_refs:
            symbol = normalize_anchor(ref)
            if symbol not in all_anchor_symbols.get(repo_name, set()) and symbol not in global_symbols:
                fail(errors, path, "related_anchors", ref, "target anchor symbol not found")

    for err in errors:
        print(f"[FAIL] {err}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
