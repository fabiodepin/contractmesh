#!/usr/bin/env python3
"""Git-aware workspace tools: diff impact, branch context, tests, docs drift."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from .documentation_impact import (
    DEPRECATION_DOCS_DRIFT_CHECK,
    STATE_NONE,
    compute_documentation_impact,
    format_documentation_impact,
)
from .workspace_search import (
    _dedupe_doc_refs,
    _doc_ref,
    _expand_related_contract_docs,
    _matching_test_docs,
    _owners_from_refs,
    _related_anchor_docs,
    _services_from_refs,
    _source_refs,
    list_drift,
    tokenize_query,
)

CODE_EXTENSIONS = {".java", ".kt", ".ts", ".tsx", ".js", ".jsx", ".go", ".py", ".yml", ".yaml"}
DOC_KINDS_FOR_DRIFT = {"contract", "adr", "integrations", "architecture"}
SYMBOL_FROM_FILE = re.compile(
    r"(?:^|/)([A-Z][A-Za-z0-9]+(?:Test|Controller|Service|Repository|Page|Client)?)\."
    r"(?:java|kt|ts|tsx|js|jsx|go|py)$"
)
MAX_CHANGED_FILES = 200


class GitCommandError(RuntimeError):
    def __init__(self, command: list[str], stderr: str) -> None:
        super().__init__(stderr.strip() or "git command failed")
        self.command = command
        self.stderr = stderr


def _run_git(workspace: Path, *args: str) -> str:
    command = ["git", *args]
    try:
        proc = subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise GitCommandError(command, str(exc)) from exc
    if proc.returncode != 0:
        raise GitCommandError(command, proc.stderr)
    return proc.stdout


def _is_git_repo(workspace: Path) -> bool:
    try:
        _run_git(workspace, "rev-parse", "--git-dir")
        return True
    except GitCommandError:
        return False


def _resolve_git_ref(workspace: Path, ref: str) -> str:
    ref = ref.strip()
    if not ref:
        raise GitCommandError(["git", "rev-parse", ref], "empty ref")
    return _run_git(workspace, "rev-parse", "--verify", ref).strip()


def git_current_branch(workspace: Path) -> str | None:
    try:
        branch = _run_git(workspace, "rev-parse", "--abbrev-ref", "HEAD").strip()
        return None if branch == "HEAD" else branch
    except GitCommandError:
        return None


def _default_base_branch(workspace: Path) -> str:
    for candidate in ("main", "master", "develop"):
        try:
            _resolve_git_ref(workspace, candidate)
            return candidate
        except GitCommandError:
            continue
    return "HEAD~1"


def _parse_name_status(output: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0].strip()
        path = parts[-1].strip()
        if status.startswith("R") and len(parts) >= 3:
            rows.append({"status": status, "path": parts[2].strip(), "old_path": parts[1].strip()})
        else:
            rows.append({"status": status, "path": path})
    return rows


def git_diff_name_status(workspace: Path, base: str, head: str) -> list[dict[str, str]]:
    base_ref = _resolve_git_ref(workspace, base)
    head_ref = _resolve_git_ref(workspace, head)
    output = _run_git(workspace, "diff", "--name-status", f"{base_ref}...{head_ref}")
    return _parse_name_status(output)


def git_worktree_changed_paths(
    workspace: Path,
    *,
    include_untracked: bool = True,
    include_staged: bool = True,
    include_unstaged: bool = True,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(path: str, status: str, change_type: str) -> None:
        path = path.strip()
        if not path or path in seen:
            return
        seen.add(path)
        rows.append({"path": path, "status": status, "change_type": change_type})

    if include_staged or include_unstaged:
        for line in _run_git(workspace, "status", "--porcelain").splitlines():
            if len(line) < 4:
                continue
            status = line[:2]
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            staged = status[0] != " " and status[0] != "?"
            unstaged = status[1] != " "
            if staged and include_staged:
                add(path, status.strip(), "staged")
            if unstaged and include_unstaged and status[:2] != "??":
                add(path, status.strip(), "unstaged")

    if include_untracked:
        for line in _run_git(workspace, "ls-files", "--others", "--exclude-standard").splitlines():
            add(line.strip(), "??", "untracked")

    return rows


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _paths_match(changed: str, indexed: str) -> bool:
    changed = _normalize_path(changed)
    indexed = _normalize_path(indexed)
    if not changed or not indexed:
        return False
    return changed == indexed or changed.endswith("/" + indexed) or indexed.endswith("/" + changed)


def _symbol_from_filename(path: str) -> str | None:
    match = SYMBOL_FROM_FILE.search(_normalize_path(path))
    return match.group(1) if match else None


def _is_code_path(path: str) -> bool:
    return Path(path).suffix.lower() in CODE_EXTENSIONS


def _is_doc_path(path: str) -> bool:
    lower = _normalize_path(path).lower()
    return lower.endswith(".md") and ("/docs/" in lower or lower.startswith("docs/"))


def _collect_changed_paths(
    workspace: Path,
    *,
    base: str | None = None,
    head: str = "HEAD",
    include_worktree: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    meta: dict[str, Any] = {
        "git_available": _is_git_repo(workspace),
        "base": base,
        "head": head,
        "include_worktree": include_worktree,
    }
    if not meta["git_available"]:
        return [], meta

    paths: list[str] = []
    seen: set[str] = set()

    def add(path: str) -> None:
        norm = _normalize_path(path)
        if norm and norm not in seen:
            seen.add(norm)
            paths.append(norm)

    if base:
        try:
            meta["base_resolved"] = _resolve_git_ref(workspace, base)
            meta["head_resolved"] = _resolve_git_ref(workspace, head)
            for row in git_diff_name_status(workspace, base, head):
                add(row["path"])
                if row.get("old_path"):
                    add(row["old_path"])
            meta["diff_mode"] = "base...head"
        except GitCommandError as exc:
            meta["git_error"] = str(exc)
            return [], meta
    elif include_worktree:
        for row in git_worktree_changed_paths(workspace):
            add(row["path"])
        meta["diff_mode"] = "worktree"
    else:
        meta["git_error"] = "base ref required when include_worktree=false"
        return [], meta

    if len(paths) > MAX_CHANGED_FILES:
        meta["truncated"] = True
        meta["changed_files_total"] = len(paths)
        paths = paths[:MAX_CHANGED_FILES]
    else:
        meta["truncated"] = False
        meta["changed_files_total"] = len(paths)

    return paths, meta


def _index_by_id(manifest: dict) -> dict[str, dict]:
    return {d.get("id", ""): d for d in manifest.get("documents", []) if d.get("id")}


def _docs_matching_paths(changed_paths: list[str], manifest: dict) -> list[dict]:
    matched: list[dict] = []
    seen: set[str] = set()
    for doc in manifest.get("documents", []):
        doc_path = doc.get("path", "")
        if not doc_path:
            continue
        if any(_paths_match(changed, doc_path) for changed in changed_paths):
            doc_id = doc.get("id", "")
            if doc_id in seen:
                continue
            seen.add(doc_id)
            matched.append(doc)
    return matched


def _symbols_from_changed_paths(changed_paths: list[str], manifest: dict) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        if not value or value in seen:
            return
        seen.add(value)
        symbols.append(value)

    for path in changed_paths:
        add(_symbol_from_filename(path))

    for doc in _docs_matching_paths(changed_paths, manifest):
        if doc.get("kind") in ("code_anchor", "test_anchor"):
            add(doc.get("symbol"))

    return symbols


def _linked_docs_for_code_changes(changed_paths: list[str], manifest: dict) -> dict[str, list[dict]]:
    by_id = _index_by_id(manifest)
    code_docs = [d for d in _docs_matching_paths(changed_paths, manifest) if d.get("kind") == "code_anchor"]
    code_doc_ids = {d.get("id") for d in code_docs}

    contracts: list[dict] = []
    adrs: list[dict] = []
    context_docs: list[dict] = []
    gaps: list[dict] = []
    anchors: list[dict] = []
    seen: set[str] = set()

    def absorb(doc: dict | None) -> None:
        if not doc:
            return
        doc_id = doc.get("id", "")
        if not doc_id or doc_id in seen:
            return
        seen.add(doc_id)
        kind = doc.get("kind")
        ref = _doc_ref(doc)
        if kind == "contract":
            contracts.append(ref)
        elif kind == "adr":
            adrs.append(ref)
        elif kind in ("integrations", "architecture"):
            context_docs.append(ref)
        elif kind == "known_gaps" or doc.get("known_gap_ids"):
            gaps.append(ref)
        elif kind == "code_anchor":
            anchors.append(ref)

    for anchor in code_docs:
        absorb(anchor)
        for doc_id in anchor.get("related_doc_ids") or []:
            absorb(by_id.get(doc_id))

    for doc in manifest.get("documents", []):
        if doc.get("kind") != "contract":
            continue
        anchor_ids = doc.get("code_anchors") or []
        if any(aid in code_doc_ids for aid in anchor_ids):
            absorb(doc)
            continue
        for aid in anchor_ids:
            anchor = by_id.get(aid)
            if not anchor:
                continue
            anchor_path = anchor.get("path", "")
            if any(_paths_match(changed, anchor_path) for changed in changed_paths):
                absorb(doc)

    expanded = _expand_related_contract_docs(manifest, [by_id[r["doc_id"]] for r in contracts if r.get("doc_id") in by_id])
    for doc in expanded:
        absorb(doc)

    return {
        "contracts": _dedupe_doc_refs(contracts),
        "adrs": _dedupe_doc_refs(adrs),
        "context_docs": _dedupe_doc_refs(context_docs),
        "known_gaps": _dedupe_doc_refs(gaps),
        "code_anchors": _dedupe_doc_refs(anchors),
    }


def _domains_from_refs(refs: list[dict[str, Any]]) -> list[str]:
    domains: set[str] = set()
    for ref in refs:
        owner = ref.get("owner") or {}
        domain = owner.get("domain")
        if domain:
            domains.add(str(domain))
        title = ref.get("title") or ""
        external = ref.get("external_id") or ""
        for token in (title, external):
            for part in re.split(r"[\s\-_/]+", token.lower()):
                if part and len(part) > 2:
                    domains.add(part)
    return sorted(domains)


def _summarize_touch(refs: list[dict[str, Any]]) -> str:
    domains = _domains_from_refs(refs)
    if not domains:
        return "No indexed domain mapping for these paths."
    preview = ", ".join(domains[:6])
    if len(domains) > 6:
        preview += ", ..."
    return f"This change likely touches: {preview}."


def _suggest_test_commands(test_paths: list[str]) -> list[str]:
    commands: list[str] = []
    seen: set[str] = set()
    java_tests = [p for p in test_paths if p.endswith("Test.java") or "/test/" in p]
    ts_tests = [p for p in test_paths if "test" in p.lower() and p.endswith((".ts", ".tsx"))]

    if java_tests:
        rel = java_tests[0]
        parts = rel.split("/", 1)
        repo = parts[0] if len(parts) == 2 else "."
        stem = Path(parts[-1]).stem
        if repo != ".":
            cmd = f"cd {repo} && ./mvnw -Dtest={stem} test"
            broad = f"cd {repo} && ./mvnw test"
        else:
            cmd = f"mvn -Dtest={stem} test"
            broad = "mvn test"
        if cmd not in seen:
            seen.add(cmd)
            commands.append(cmd)
        if broad not in seen:
            seen.add(broad)
            commands.append(broad)

    if ts_tests:
        rel = ts_tests[0]
        parts = rel.split("/", 1)
        repo = parts[0] if len(parts) == 2 else "."
        cmd = f"cd {repo} && npm test" if repo != "." else "npm test"
        if cmd not in seen:
            seen.add(cmd)
            commands.append(cmd)

    if not commands and test_paths:
        commands.append("# Review related test files manually; no default runner matched.")
    return commands


def _collect_docs_possibly_stale(changed_paths: list[str], manifest: dict) -> list[dict[str, Any]]:
    """Docs linked to changed code that were not modified in the same diff."""
    changed_set = {_normalize_path(p) for p in changed_paths}
    by_id = _index_by_id(manifest)
    stale: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(entry: dict[str, Any]) -> None:
        key = f"{entry.get('path')}::{entry.get('code_path')}"
        if key in seen:
            return
        seen.add(key)
        stale.append(entry)

    code_changes = [
        p
        for p in changed_paths
        if _is_code_path(p) and not p.startswith(".contractmesh/")
    ]
    code_docs = _docs_matching_paths(code_changes, manifest)
    code_anchor_docs = [d for d in code_docs if d.get("kind") == "code_anchor"]

    for anchor in code_anchor_docs:
        code_path = anchor.get("path", "")
        symbol = anchor.get("symbol", "")
        for doc_id in anchor.get("related_doc_ids") or []:
            related = by_id.get(doc_id)
            if not related or related.get("kind") not in DOC_KINDS_FOR_DRIFT:
                continue
            doc_path = _normalize_path(related.get("path", ""))
            if doc_path in changed_set:
                continue
            add(
                {
                    "path": doc_path,
                    "kind": related.get("kind"),
                    "external_id": related.get("external_id") or related.get("id"),
                    "title": related.get("title", ""),
                    "code_path": code_path,
                    "symbol": symbol,
                    "reason": (
                        f"Linked code changed ({symbol or code_path}) but this doc was not updated."
                    ),
                }
            )

    for doc in manifest.get("documents", []):
        if doc.get("kind") != "contract":
            continue
        for aid in doc.get("code_anchors") or []:
            anchor = by_id.get(aid)
            if not anchor:
                continue
            anchor_path = _normalize_path(anchor.get("path", ""))
            if not any(_paths_match(changed, anchor_path) for changed in code_changes):
                continue
            contract_path = _normalize_path(doc.get("path", ""))
            if contract_path in changed_set:
                continue
            add(
                {
                    "path": contract_path,
                    "kind": "contract",
                    "external_id": doc.get("external_id"),
                    "title": doc.get("title", ""),
                    "code_path": anchor_path,
                    "symbol": anchor.get("symbol"),
                    "reason": (
                        f"Contract references changed code ({anchor.get('symbol')}) "
                        "but the contract file was not modified."
                    ),
                }
            )

    return stale


def _confirmed_findings_from_manifest(manifest: dict) -> list[dict[str, Any]]:
    """Map indexed drift findings into documentation_impact confirmed inputs."""
    out: list[dict[str, Any]] = []
    for finding in list_drift(manifest).get("findings") or []:
        drift_type = str(finding.get("drift_type") or "")
        if drift_type == "anchor_unresolved":
            out.append(
                {
                    "drift_type": "anchor_unresolved",
                    "summary": finding.get("summary"),
                    "path": finding.get("path"),
                    "external_id": finding.get("external_id"),
                }
            )
        elif drift_type in ("semantic_mismatch", "contract_vs_code"):
            # Only treat as confirmed semantic when explicitly typed as such.
            if drift_type == "semantic_mismatch":
                out.append(
                    {
                        "drift_type": "semantic_mismatch",
                        "summary": finding.get("summary"),
                        "path": finding.get("path"),
                        "external_id": finding.get("external_id"),
                    }
                )
    return out


def documentation_impact(
    workspace: Path,
    manifest: dict,
    *,
    base: str | None = None,
    head: str = "HEAD",
    include_worktree: bool = True,
    changed_paths: list[str] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Git/path wrapper around compute_documentation_impact (same payload everywhere)."""
    git_meta: dict[str, Any] = {}
    paths = list(changed_paths or [])
    if not paths:
        if base is None and not include_worktree:
            base = _default_base_branch(workspace)
        paths, git_meta = _collect_changed_paths(
            workspace,
            base=base if not include_worktree else None,
            head=head,
            include_worktree=include_worktree,
        )
        if git_meta.get("git_error") and not paths:
            return {"git": git_meta, **compute_documentation_impact(manifest=manifest)}, git_meta[
                "git_error"
            ]

    impact = compute_documentation_impact(
        changed_paths=paths,
        manifest=manifest,
        confirmed_findings=_confirmed_findings_from_manifest(manifest),
    )
    impact["git"] = git_meta
    impact["changed_files"] = paths
    return impact, None


def pr_impact(
    workspace: Path,
    manifest: dict,
    local_by_id: dict[str, dict],
    *,
    base: str | None = None,
    head: str = "HEAD",
    include_worktree: bool = False,
    test_limit: int = 12,
) -> tuple[dict[str, Any], str | None]:
    """Map git diff paths to PR impact: contracts, ADRs, anchors, tests, gaps, docs impact."""
    if base is None and not include_worktree:
        base = _default_base_branch(workspace)

    changed_paths, git_meta = _collect_changed_paths(
        workspace,
        base=base if not include_worktree else None,
        head=head,
        include_worktree=include_worktree,
    )
    if git_meta.get("git_error") and not changed_paths:
        return {"git": git_meta}, git_meta["git_error"]

    linked = _linked_docs_for_code_changes(changed_paths, manifest)
    symbols = _symbols_from_changed_paths(changed_paths, manifest)
    tests = _matching_test_docs(
        workspace,
        manifest,
        local_by_id,
        repo_filters=[],
        symbols=symbols,
        query_tokens=tokenize_query(" ".join(symbols)),
        limit=test_limit,
    )
    doc_impact = compute_documentation_impact(
        changed_paths=changed_paths,
        manifest=manifest,
        confirmed_findings=_confirmed_findings_from_manifest(manifest),
    )
    # Compat: flatten possible/confirmed docs for older consumers.
    docs_possibly_stale = [
        {
            "path": d.get("path"),
            "kind": d.get("kind"),
            "external_id": d.get("id"),
            "title": d.get("title"),
            "reasons": d.get("reasons"),
            "reason": "; ".join(
                str(r.get("kind")) for r in (d.get("reasons") or []) if r.get("kind")
            ),
        }
        for d in doc_impact.get("documents") or []
    ]
    all_refs = (
        linked["contracts"]
        + linked["adrs"]
        + linked["code_anchors"]
        + linked["known_gaps"]
        + tests
        + [{"path": d["path"], "kind": d.get("kind"), "repo": ""} for d in docs_possibly_stale]
    )

    result = {
        "changed_files": changed_paths,
        "contracts": linked["contracts"],
        "adrs": linked["adrs"],
        "code_anchors": linked["code_anchors"],
        "test_anchors": tests,
        "known_gaps": linked["known_gaps"],
        "suggested_test_commands": _suggest_test_commands([t["path"] for t in tests]),
        "documentation_impact": doc_impact,
        "docs_possibly_stale": docs_possibly_stale,
        "provenance": {
            "sources_consulted": _source_refs(all_refs),
            "retrieval_strategy": "git diff paths mapped to indexed contracts, anchors and tests",
            "git": git_meta,
        },
    }
    if doc_impact.get("state") != STATE_NONE:
        result["documentation_impact_text"] = format_documentation_impact(doc_impact)
    return result, None


def docs_drift_check(
    workspace: Path,
    manifest: dict,
    *,
    base: str | None = None,
    head: str = "HEAD",
    include_worktree: bool = True,
) -> tuple[dict[str, Any], str | None]:
    """Deprecated alias for documentation_impact (possible-impact signal).

    Kept for MCP/CLI compatibility. Prefer documentation_impact / `docs impact`.
    """
    impact, err = documentation_impact(
        workspace,
        manifest,
        base=base,
        head=head,
        include_worktree=include_worktree,
    )
    if err:
        return impact, err

    alerts = [
        {
            "path": d.get("path"),
            "kind": d.get("kind"),
            "external_id": d.get("id"),
            "title": d.get("title"),
            "reasons": d.get("reasons"),
            "reason": "; ".join(
                str(r.get("kind")) for r in (d.get("reasons") or []) if r.get("kind")
            ),
        }
        for d in impact.get("documents") or []
    ]
    code_changes = [
        p
        for p in (impact.get("changed_files") or [])
        if _is_code_path(p) and not p.startswith(".contractmesh/")
    ]
    updated_docs = [
        _normalize_path(p)
        for p in (impact.get("changed_files") or [])
        if _is_doc_path(p)
    ]
    return {
        **DEPRECATION_DOCS_DRIFT_CHECK,
        "documentation_impact": impact,
        "summary": impact.get("summary")
        or (
            f"{len(alerts)} potential docs drift alert(s)."
            if alerts
            else "No docs drift detected for the current diff."
        ),
        "git": impact.get("git") or {},
        "changed_files": impact.get("changed_files") or [],
        "code_files_changed": code_changes,
        "docs_files_changed": updated_docs,
        "alerts": alerts,
        "docs_possibly_stale": alerts,
        "alert_count": len(alerts),
        "provenance": {
            "retrieval_strategy": "documentation_impact (deprecated docs_drift_check alias)",
        },
    }, None


def branch_context(
    workspace: Path,
    manifest: dict,
    local_by_id: dict[str, dict],
    *,
    base: str | None = None,
    include_uncommitted: bool = True,
) -> tuple[dict[str, Any], str | None]:
    """Current branch, local changes and related indexed contracts."""
    if not _is_git_repo(workspace):
        return {}, "workspace is not a git repository"

    branch = git_current_branch(workspace)
    compare_base = base or _default_base_branch(workspace)

    changed_local: list[str] = []
    if include_uncommitted:
        for row in git_worktree_changed_paths(workspace):
            changed_local.append(row["path"])

    diff_result, err = pr_impact(
        workspace,
        manifest,
        local_by_id,
        base=compare_base,
        head="HEAD",
        include_worktree=False,
    )
    if err and not diff_result.get("changed_files"):
        diff_paths: list[str] = []
        git_meta = diff_result.get("git", {})
    else:
        diff_paths = diff_result.get("changed_files", [])
        git_meta = diff_result.get("git", {})

    all_paths = _dedupe_doc_refs(
        [{"path": p} for p in dict.fromkeys([*changed_local, *diff_paths])]
    )
    paths = [p["path"] for p in all_paths]
    linked = _linked_docs_for_code_changes(paths, manifest)

    return {
        "branch": branch,
        "compare_base": compare_base,
        "uncommitted_files": changed_local,
        "committed_diff_files": diff_paths,
        "all_changed_files": paths,
        "git": git_meta,
        "contracts": linked["contracts"],
        "adrs": linked["adrs"],
        "context_docs": linked["context_docs"],
        "known_gaps": linked["known_gaps"],
        "code_anchors": linked["code_anchors"],
        "summary": _summarize_touch(linked["contracts"]),
        "provenance": {
            "note": "Combines branch diff against base plus uncommitted worktree changes.",
            "sources_consulted": _source_refs(
                linked["contracts"] + linked["adrs"] + linked["context_docs"]
            ),
        },
    }, None


def suggest_tests_for_diff(
    workspace: Path,
    manifest: dict,
    local_by_id: dict[str, dict],
    *,
    base: str | None = None,
    head: str = "HEAD",
    include_worktree: bool = True,
    limit: int = 12,
) -> tuple[dict[str, Any], str | None]:
    """Suggest tests for files changed in git diff or worktree."""
    if base is None and not include_worktree:
        base = _default_base_branch(workspace)

    changed_paths, git_meta = _collect_changed_paths(
        workspace,
        base=base if not include_worktree else None,
        head=head,
        include_worktree=include_worktree,
    )
    if git_meta.get("git_error") and not changed_paths:
        return {"git": git_meta}, git_meta["git_error"]

    symbols = _symbols_from_changed_paths(changed_paths, manifest)
    tests = _matching_test_docs(
        workspace,
        manifest,
        local_by_id,
        repo_filters=[],
        symbols=symbols,
        query_tokens=tokenize_query(" ".join(symbols)),
        limit=limit,
    )
    test_paths = [t["path"] for t in tests]

    return {
        "summary": "Run these tests before opening a PR." if tests else "No indexed tests matched the diff.",
        "git": git_meta,
        "changed_files": changed_paths,
        "symbols_considered": symbols,
        "related_tests": tests,
        "suggested_test_commands": _suggest_test_commands(test_paths),
        "count": len(tests),
    }, None
