"""Explain whether a path is allowlisted and whether it becomes an index artifact."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .build_code_anchors import (
    collect_go_sources,
    collect_go_tests,
    collect_java_sources,
    collect_java_tests,
    collect_python_sources,
    collect_python_tests,
    collect_ts_sources,
    collect_ts_tests,
    collect_vue_sources,
)
from .build_search_index import OPENAPI_BASENAMES, infer_kind, manifest_doc_roots
from .index_policy import IndexPolicy, load_index_policy
from .workspace_manifest import load_workspace_manifest

CONFIG_BASENAMES = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "vite.config.ts",
    "vite.config.js",
    "tsconfig.json",
    "docker-compose.yml",
    "docker-compose.prod.yml",
    "dockerfile",
}


def _under_any(rel: str, roots: list[str]) -> bool:
    norm = rel.replace("\\", "/").lower().strip("/")
    for root in roots:
        root_n = root.strip("/").lower()
        if not root_n:
            continue
        if norm == root_n or norm.startswith(root_n + "/"):
            return True
    return False


def _markdown_would_be_indexed(
    *,
    rel: str,
    roots: dict[str, list[str]],
    policy: IndexPolicy,
) -> tuple[bool, str | None]:
    """Mirror collect_workspace_docs / collect_repo_docs eligibility for explain."""
    rel_parts = {part.lower() for part in Path(rel).parts}
    if "generated" in rel_parts:
        return False, (
            "markdown_under_generated — search-index collectors skip directories "
            "named generated"
        )

    basename = Path(rel).name
    # Only repo-root AGENTS.md files are collected (not nested package copies).
    if basename == "AGENTS.md":
        for _name, repo_path in (policy.repo_paths or {}).items():
            if repo_path in (".", ""):
                if rel == "AGENTS.md":
                    return True, None
            else:
                prefix = repo_path.rstrip("/")
                if rel == f"{prefix}/AGENTS.md":
                    return True, None
        if rel == "AGENTS.md":
            return True, None
        return False, "agents_md_not_at_repo_root"

    # Workspace-root docs tree (collect_workspace_docs walks docs/**).
    if rel.startswith("docs/") or _under_any(
        rel, roots["adrs"] + roots["contracts"] + roots["gaps"]
    ):
        return True, None

    # Repo-prefixed paths: docs/ai, AGENTS.md, and manifest roots relative to each repo.
    for _name, repo_path in (policy.repo_paths or {}).items():
        if repo_path in (".", ""):
            local = rel
        else:
            prefix = repo_path.rstrip("/")
            if rel == prefix:
                continue
            if not rel.startswith(prefix + "/"):
                continue
            local = rel[len(prefix) + 1 :]
        if local == "AGENTS.md" or local.startswith("docs/ai/"):
            return True, None
        # Match collect_repo_docs fallbacks for conventional layouts.
        local_roots = list(
            dict.fromkeys(
                [
                    *roots["adrs"],
                    *roots["contracts"],
                    *roots["gaps"],
                    "docs/adrs",
                    "docs/adr",
                    "docs/contracts",
                    "docs/contract",
                ]
            )
        )
        if _under_any(local, local_roots):
            return True, None
    return False, "markdown_outside_configured_doc_roots"


def explain_index_path(workspace: Path, path: str | Path) -> dict[str, Any]:
    """Combine IndexPolicy decision with whether collectors would index the path."""
    policy = load_index_policy(workspace)
    decision = policy.explain(path)
    payload = decision.as_dict()
    payload["note"] = (
        "IndexPolicy decides whether ContractMesh may read a path. "
        "Only curated markdown docs and code/test anchors enter the search index."
    )
    if not decision.allowed:
        payload["indexed_as"] = None
        payload["why_not_indexed"] = f"blocked_by_policy:{decision.reason}"
        return payload

    rel = decision.path
    abs_path = workspace / rel
    suffix = abs_path.suffix.lower()
    name = abs_path.name.lower()
    manifest = load_workspace_manifest(workspace)
    roots = manifest_doc_roots(manifest)

    if suffix == ".md":
        kind = infer_kind(
            rel,
            abs_path.name,
            True,
            adr_roots=roots["adrs"] or None,
            contract_roots=roots["contracts"] or None,
        )
        would_index, why_not = _markdown_would_be_indexed(rel=rel, roots=roots, policy=policy)
        if would_index:
            payload["indexed_as"] = "markdown_doc"
            payload["doc_kind"] = kind
            payload["why_not_indexed"] = None
            return payload
        payload["indexed_as"] = None
        payload["why_not_indexed"] = why_not
        return payload

    if name in CONFIG_BASENAMES or rel.lower().endswith(tuple(f"/{b}" for b in CONFIG_BASENAMES)):
        payload["indexed_as"] = None
        payload["why_not_indexed"] = (
            "config_boundary_only — allowlisted for security/review, not a search document "
            "or code anchor"
        )
        return payload

    if name in OPENAPI_BASENAMES or Path(rel).name.lower() in {
        b.lower() for b in OPENAPI_BASENAMES
    }:
        # discover_openapi_source_files looks at shallow/common locations under repos.
        payload["indexed_as"] = "openapi_spec_candidate"
        payload["why_not_indexed"] = None
        payload["note"] = (
            payload["note"]
            + " OpenAPI files are indexed when discovered at standard locations "
            "and index.openapi is enabled."
        )
        return payload

    if suffix == ".sql" or "prisma/" in rel.replace("\\", "/").lower():
        payload["indexed_as"] = None
        payload["why_not_indexed"] = "no_sql_or_prisma_collector"
        return payload

    if suffix in {".ts", ".tsx"}:
        # Prefer the most specific configured repo path that contains this file
        # (same resolution as IndexPolicy / collect_code_anchors).
        _repo_name, repo_path = policy.resolve_repo(rel)
        if not repo_path:
            repo_path = "."
        collected = {p.resolve() for p in collect_ts_sources(workspace, repo_path)}
        collected.update(p.resolve() for p in collect_ts_tests(workspace, repo_path))
        if abs_path.resolve() in collected:
            payload["indexed_as"] = "code_anchor"
            payload["why_not_indexed"] = None
            return payload
        payload["indexed_as"] = None
        payload["why_not_indexed"] = (
            "typescript_not_in_curated_patterns — anchors collect */src files matching "
            "patterns such as *Service.ts, *Page.tsx, *Store.ts, *-router.ts, "
            "*-repository.ts, *-middleware.ts, config.ts, src/<module>/index.ts, "
            "system/types/**, global/types/** (not every .ts file)"
        )
        return payload

    if suffix == ".vue":
        _repo_name, repo_path = policy.resolve_repo(rel)
        if not repo_path:
            repo_path = "."
        collected = {p.resolve() for p in collect_vue_sources(workspace, repo_path)}
        if abs_path.resolve() in collected and abs_path.stem[:1].isupper():
            payload["indexed_as"] = "code_anchor"
            payload["why_not_indexed"] = None
            return payload
        payload["indexed_as"] = None
        payload["why_not_indexed"] = (
            "vue_not_in_curated_patterns — anchors collect PascalCase SFCs under "
            "src/views/*.vue, src/system/components/**, and src/global/components/**"
        )
        return payload

    if suffix in {".py", ".java", ".kt", ".go"}:
        _repo_name, repo_path = policy.resolve_repo(rel)
        if not repo_path:
            repo_path = "."
        if suffix == ".py":
            collected = collect_python_sources(workspace, repo_path)
            collected += collect_python_tests(workspace, repo_path)
            why = (
                "python_outside_collector_layouts — Python anchors come from "
                "src/**/*.py, top-level *.py, and tests/** (excluding non-test layouts)"
            )
        elif suffix in {".java", ".kt"}:
            collected = collect_java_sources(workspace, repo_path, policy)
            collected += collect_java_tests(workspace, repo_path, policy)
            why = (
                "java_outside_collector_layouts — Java/Kotlin anchors come from "
                "src/main/java|kotlin and test trees with curated path/name hints"
            )
        else:
            collected = collect_go_sources(workspace, repo_path, policy)
            collected += collect_go_tests(workspace, repo_path, policy)
            why = (
                "go_outside_collector_layouts — Go anchors come from internal/ and cmd/"
            )
        if abs_path.resolve() in {p.resolve() for p in collected}:
            payload["indexed_as"] = "code_anchor"
            payload["why_not_indexed"] = None
            return payload
        payload["indexed_as"] = None
        payload["why_not_indexed"] = why
        return payload

    payload["indexed_as"] = None
    payload["why_not_indexed"] = "no_collector_for_file_type"
    return payload
