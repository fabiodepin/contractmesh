#!/usr/bin/env python3
"""Load the ContractMesh workspace manifest from contractmesh.yml."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_DOCS = {
    "contracts": ["docs/ai/contracts"],
    "adrs": ["docs/adrs"],
    "gaps": ["docs/ai/known-gaps.md"],
}
DEFAULT_LINT = {
    "require_owner": False,
    "require_ids": False,
    "require_valid_crosslinks": False,
}
DEFAULT_INDEX = {
    # index.mode is required in contractmesh.yml — never invent a silent default.
    "include": [],
    "exclude": [],
    "structural_graph": False,
    "git_mining": False,
    "embeddings": False,
    "openapi": False,
    "drift": False,
    "adapters": [],
}
DEFAULT_PREFLIGHT = {
    "high_min_score": 6,
    "medium_min_score": 3,
    "gap_weight": 3,
    "no_tests_weight": 2,
    "drift_weight": 2,
    "contract_weight": 2,
    "multi_contract_weight": 1,
    "adr_weight": 1,
    "method_weight": 1,
    "low_tests_weight": 1,
    "soft_block_enabled": True,
    "soft_block_require": ["HIGH"],
}


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value


def load_contractmesh_yml(path: Path) -> dict[str, Any]:
    """Parse the small YAML subset used by contractmesh.yml."""
    lines = path.read_text(encoding="utf-8").splitlines()
    data: dict[str, Any] = {}
    section: str | None = None
    subsection: str | None = None
    current_repo: dict[str, str] | None = None

    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()

        if indent == 0 and line.endswith(":"):
            section = line[:-1]
            subsection = None
            if section == "repos":
                data.setdefault("repos", [])
            else:
                data.setdefault(section, {})
            continue

        if indent == 0 and ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = parse_scalar(value)
            section = None
            subsection = None
            continue

        if section == "repos":
            if indent == 2 and line.startswith("- "):
                current_repo = {}
                data.setdefault("repos", []).append(current_repo)
                rest = line[2:].strip()
                if rest and ":" in rest:
                    key, value = rest.split(":", 1)
                    current_repo[key.strip()] = str(parse_scalar(value))
                continue
            if indent >= 4 and current_repo is not None and ":" in line:
                key, value = line.split(":", 1)
                current_repo[key.strip()] = str(parse_scalar(value))
            continue

        if section in ("docs", "lint", "index", "preflight"):
            target = data.setdefault(section, {})
            if indent == 2 and line.endswith(":"):
                subsection = line[:-1]
                target.setdefault(subsection, [])
                continue
            if indent == 2 and ":" in line:
                key, value = line.split(":", 1)
                target[key.strip()] = parse_scalar(value)
                continue
            if indent == 4 and subsection and line.startswith("- "):
                target.setdefault(subsection, []).append(line[2:].strip())
                continue

    return data


def normalize_manifest(data: dict[str, Any], source: str) -> dict[str, Any]:
    repos = data.get("repos") or []
    normalized_repos: list[dict[str, str]] = []
    for item in repos:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip().strip("/")
        name = str(item.get("name") or Path(path).name).strip()
        if path:
            normalized_repos.append({"path": path, "name": name})
    docs = dict(DEFAULT_DOCS)
    docs.update(data.get("docs") or {})
    lint = dict(DEFAULT_LINT)
    lint.update(data.get("lint") or {})
    index = dict(DEFAULT_INDEX)
    raw_index = data.get("index") or {}
    for key, value in raw_index.items():
        if key == "adapters":
            if isinstance(value, list):
                index["adapters"] = [str(v) for v in value]
            continue
        if key in ("include", "exclude"):
            if isinstance(value, list):
                index[key] = [str(v).strip().strip("\"'") for v in value if str(v).strip()]
            elif isinstance(value, str) and value.strip():
                index[key] = [value.strip().strip("\"'")]
            else:
                index[key] = []
            continue
        if key == "mode":
            # Preserve the declared value (including invalid) for fail-closed validation.
            index["mode"] = str(value).strip().lower()
            continue
        index[key] = value
    from .index_policy import normalize_index_security

    index = normalize_index_security(index)
    preflight = dict(DEFAULT_PREFLIGHT)
    raw_preflight = data.get("preflight") or {}
    for key, value in raw_preflight.items():
        if key == "soft_block_require" and isinstance(value, list):
            preflight["soft_block_require"] = [str(v).upper() for v in value]
            continue
        preflight[key] = value
    return {
        "name": data.get("name", "workspace"),
        "mode": data.get("mode", "default"),
        "workspace_mapping_version": data.get("workspace_mapping_version", "v1"),
        "repos": normalized_repos,
        "docs": docs,
        "lint": lint,
        "index": index,
        "preflight": preflight,
        "source": source,
    }


def load_workspace_manifest(workspace: Path) -> dict[str, Any]:
    manifest_path = workspace / "contractmesh.yml"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"contractmesh.yml not found under {workspace}. Run: contractmesh init --here"
        )
    return normalize_manifest(load_contractmesh_yml(manifest_path), "contractmesh.yml")


def repo_specs(manifest: dict[str, Any]) -> list[str]:
    return [f"{r['name']}={r['path']}" for r in manifest.get("repos", [])]


def validate_manifest(workspace: Path, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    if not manifest.get("repos"):
        errors.append(f"{manifest['source']}: repos must contain at least one repository")
    for i, repo in enumerate(manifest.get("repos", [])):
        path = repo.get("path", "")
        name = repo.get("name", "")
        where = f"{manifest['source']}: repos[{i}]"
        if not path:
            errors.append(f"{where}.path is required")
        if not name:
            errors.append(f"{where}.name is required")
        if name in seen:
            errors.append(f"{where}.name duplicates '{name}'")
        seen.add(name)
        if path and not (workspace / path).is_dir():
            errors.append(f"{where}.path '{path}' does not exist")
    for key in ("contracts", "adrs", "gaps"):
        value = (manifest.get("docs") or {}).get(key)
        if not isinstance(value, list):
            errors.append(f"{manifest['source']}: docs.{key} must be a list")
    from .index_policy import validate_index_security

    repo_names = [r.get("name", "") for r in manifest.get("repos") or []]
    errors.extend(
        validate_index_security(
            manifest.get("index") or {},
            repo_names=repo_names,
            source=str(manifest.get("source") or "contractmesh.yml"),
        )
    )
    return errors


def main(argv: list[str]) -> int:
    workspace = Path(argv[2] if len(argv) > 2 else ".").resolve()
    manifest = load_workspace_manifest(workspace)
    cmd = argv[1] if len(argv) > 1 else "json"
    if cmd == "json":
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    elif cmd == "repos-csv":
        print(",".join(repo_specs(manifest)))
    elif cmd == "repos-lines":
        for repo in manifest.get("repos", []):
            print(repo["path"])
    elif cmd == "version":
        print(manifest.get("workspace_mapping_version", "v1"))
    elif cmd == "validate":
        errors = validate_manifest(workspace, manifest)
        for err in errors:
            print(f"[FAIL] {err}")
        return 1 if errors else 0
    else:
        print("Usage: workspace_manifest.py [json|repos-csv|repos-lines|version|validate] [workspace]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
