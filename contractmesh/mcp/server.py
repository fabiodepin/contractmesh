#!/usr/bin/env python3
"""MCP server: workspace knowledge index (search, chunks, gaps, status)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from contractmesh.engine.git_workspace_tools import (
    branch_context as compute_branch_context,
    docs_drift_check as compute_docs_drift_check,
    documentation_impact as compute_documentation_impact,
    pr_impact as compute_pr_impact,
    suggest_tests_for_diff as compute_suggest_tests_for_diff,
)
from contractmesh.engine.preflight_change import preflight_change as compute_preflight_change
from contractmesh.engine.workspace_search import (
    DEFAULT_MAX_CHARS,
    FETCH_HITS_DEFAULT_LIMIT,
    FETCH_HITS_DEFAULT_MAX_CHARS_PER_CHUNK,
    FETCH_HITS_DEFAULT_MAX_RELATED_ANCHORS,
    FETCH_HITS_DEFAULT_MAX_TOTAL_CHARS,
    IndexNotFoundError,
    doc_path_from_manifest,
    evolution_trace as compute_evolution_trace,
    fetch_hits as compute_fetch_hits,
    get_workspace_root,
    impact_analysis as compute_impact_analysis,
    index_status as compute_index_status,
    list_drift as compute_list_drift,
    list_known_gaps,
    load_index,
    orient_workspace as compute_orient_workspace,
    read_chunk_by_id,
    read_doc_chunks,
    related_tests as compute_related_tests,
    run_build,
    search_documents,
    search_hit_to_dict,
)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("workspace-knowledge", log_level="WARNING")


def _workspace() -> Path:
    return get_workspace_root()


def _load_or_error(rebuild_if_missing: bool = False) -> tuple[dict, dict[str, dict]]:
    workspace = _workspace()
    try:
        return load_index(workspace)
    except IndexNotFoundError:
        if rebuild_if_missing:
            run_build(workspace)
            return load_index(workspace)
        raise


@mcp.tool()
def fetch_hits(
    query: str = "",
    repo: str | list[str] | None = None,
    kind: str | list[str] | None = None,
    gap: str | None = None,
    symbol: str | None = None,
    limit: int = FETCH_HITS_DEFAULT_LIMIT,
    max_chars_per_chunk: int = FETCH_HITS_DEFAULT_MAX_CHARS_PER_CHUNK,
    include_main_chunk: bool = True,
    include_related_anchors: bool = True,
    max_related_anchors_per_hit: int = FETCH_HITS_DEFAULT_MAX_RELATED_ANCHORS,
    max_total_chars: int = FETCH_HITS_DEFAULT_MAX_TOTAL_CHARS,
    rebuild_if_missing: bool = False,
) -> str:
    """Primary retrieval: search + chunk text in one call (replaces search_docs + many get_chunk).

    Examples:
    - Cross-repo contract lookup: query="example greeting", kind=["contract"],
      repo=["app","web"]
    - Known gap: gap="APP-KG-001"
    - Symbols only: include_main_chunk=false, query="ExampleService", kind=["code_anchor"]

    If truncated=true, use get_chunk(chunk_id) or get_doc_chunks(doc_id) for missing text.
    truncation_reason: max_total_chars | max_chars_per_chunk
    """
    try:
        manifest, local_by_id = _load_or_error(rebuild_if_missing)
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )

    result, message = compute_fetch_hits(
        _workspace(),
        manifest,
        local_by_id,
        query=query,
        gap=gap,
        symbol=symbol,
        repo=repo,
        kind=kind,
        limit=limit,
        max_chars_per_chunk=max_chars_per_chunk,
        include_main_chunk=include_main_chunk,
        include_related_anchors=include_related_anchors,
        max_related_anchors_per_hit=max_related_anchors_per_hit,
        max_total_chars=max_total_chars,
    )
    if message:
        return json.dumps({"error": "invalid_query", "message": message}, ensure_ascii=False)

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def search_docs(
    query: str = "",
    repo: str | list[str] | None = None,
    kind: str | list[str] | None = None,
    gap: str | None = None,
    symbol: str | None = None,
    limit: int = 10,
    rebuild_if_missing: bool = False,
) -> str:
    """Locate documents only (metadata + snippets). Prefer fetch_hits for normal Q&A.

    Use when you need more hits (higher limit), a different ranking pass, or no chunk text.
    Priority: symbol exact > gap exact > keyword > repo/kind filters.

    Example (deep dive after fetch_hits): symbol="EmailAccountService", kind=["code_anchor"]
    """
    try:
        manifest, local_by_id = _load_or_error(rebuild_if_missing)
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )

    hits, message = search_documents(
        _workspace(),
        manifest,
        local_by_id,
        query=query,
        gap=gap,
        symbol=symbol,
        repo=repo,
        kind=kind,
        limit=limit,
    )
    if message:
        return json.dumps({"error": "invalid_query", "message": message}, ensure_ascii=False)

    return json.dumps(
        {"hits": [search_hit_to_dict(h) for h in hits], "count": len(hits)},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def get_chunk(chunk_id: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Load one chunk by id. Use after fetch_hits when truncated=true.

    chunk_id format: doc:{repo}:...#{n} or anchor:{repo}:{path}#{symbol}#{n}
    Do not hardcode chunk_id in human docs — ids change after index rebuild.
    """
    try:
        manifest, local_by_id = load_index(_workspace())
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )

    row = read_chunk_by_id(
        _workspace(),
        local_by_id,
        chunk_id,
        manifest=manifest,
        max_chars=max_chars,
    )
    if not row:
        return json.dumps(
            {
                "error": "chunk_not_found",
                "chunk_id": chunk_id,
                "hint": "Expected doc:{repo}:...#{n} or anchor:{repo}:{path}#{symbol}#{n}",
            },
            ensure_ascii=False,
        )
    return json.dumps(row, ensure_ascii=False, indent=2)


@mcp.tool()
def get_doc_chunks(
    doc_id: str,
    max_chunks: int = 5,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Load multiple sections of one document. Use when fetch_hits truncated and you need more ## sections.

    Prefer stable doc_id (e.g. doc:app:docs:contracts:example-contract) over chunk suffix #n.
    """
    try:
        manifest, local_by_id = load_index(_workspace())
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )

    chunks = read_doc_chunks(
        _workspace(),
        local_by_id,
        doc_id,
        manifest=manifest,
        max_chunks=max_chunks,
        max_chars=max_chars,
    )
    if chunks is None:
        return json.dumps(
            {"error": "doc_not_found", "doc_id": doc_id},
            ensure_ascii=False,
        )
    return json.dumps(
        {"doc_id": doc_id, "path": doc_path_from_manifest(manifest, doc_id), "chunks": chunks},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def list_gaps(
    gap_id: str | None = None,
    prefix: str | None = None,
    repo: str | list[str] | None = None,
) -> str:
    """List indexed known-gap IDs (from known-gaps.md and contracts).

    Example: prefix="APP-KG" or gap_id="APP-KG-001"
    """
    try:
        manifest, _ = load_index(_workspace())
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )

    result = list_known_gaps(manifest, repo=repo, prefix=prefix, gap_id=gap_id)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def impact_analysis(
    query: str = "",
    repo: str | list[str] | None = None,
    gap: str | None = None,
    symbol: str | None = None,
    limit: int = 5,
    rebuild_if_missing: bool = False,
) -> str:
    """Build a deterministic Change Impact Graph for a rule or behavior.

    Use for questions like: "What do I need to change to modify this rule?"
    Returns contracts, ADRs, owners, services, code anchors, test anchors,
    known gaps and provenance. This is deterministic evidence gathering, not an
    autonomous edit plan.
    """
    try:
        manifest, local_by_id = _load_or_error(rebuild_if_missing)
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )

    result, message = compute_impact_analysis(
        _workspace(),
        manifest,
        local_by_id,
        query=query,
        gap=gap,
        symbol=symbol,
        repo=repo,
        limit=limit,
    )
    if message:
        return json.dumps({"error": "invalid_query", "message": message}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def preflight_change(
    symbol: str,
    repo: str | list[str] | None = None,
    limit: int = 8,
    rebuild_if_missing: bool = False,
) -> str:
    """Preflight before editing a symbol — compact card + details JSON.

    Example: preflight_change(symbol="EmailAccountService.create")

    Returns:
    - card.text — scannable summary (Risk, Why, Review, Run)
    - agent_policy — soft block when risk is HIGH (requires_confirmation)
    - details — full contracts, gaps, tests, drift, provenance
    """
    try:
        manifest, local_by_id = _load_or_error(rebuild_if_missing)
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )

    result, message = compute_preflight_change(
        _workspace(),
        manifest,
        local_by_id,
        symbol=symbol,
        repo=repo,
        limit=limit,
    )
    if message:
        return json.dumps({"error": "invalid_query", "message": message}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def related_tests(
    query: str = "",
    repo: str | list[str] | None = None,
    symbol: str | None = None,
    limit: int = 8,
    rebuild_if_missing: bool = False,
) -> str:
    """Find tests related to a contract, behavior query, or code symbol.

    Uses indexed test anchors plus contract/code-anchor links. Includes owners
    and services when available. Rebuild the index after adding tests.
    """
    try:
        manifest, local_by_id = _load_or_error(rebuild_if_missing)
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )

    result, message = compute_related_tests(
        _workspace(),
        manifest,
        local_by_id,
        query=query,
        symbol=symbol,
        repo=repo,
        limit=limit,
    )
    if message:
        return json.dumps({"error": "invalid_query", "message": message}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def orient_workspace(
    repo: str | list[str] | None = None,
    rebuild_if_missing: bool = False,
) -> str:
    """Workspace orientation: routes, controller/service/repository layers, top contracts.

    Structural edges are inferred (trust_level: inferred). Prefer contracts for behavior.
    """
    try:
        manifest, _ = _load_or_error(rebuild_if_missing)
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )
    result = compute_orient_workspace(_workspace(), manifest, repo=repo)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def list_drift(rebuild_if_missing: bool = False) -> str:
    """List drift findings (contract vs code/openapi/client-server/anchors).

    Requires index.drift: true in contractmesh.yml and a fresh index build.
    """
    try:
        manifest, _ = _load_or_error(rebuild_if_missing)
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )
    return json.dumps(compute_list_drift(manifest), ensure_ascii=False, indent=2)


@mcp.tool()
def evolution_trace(
    contract_id: str | None = None,
    symbol: str | None = None,
    rebuild_if_missing: bool = False,
) -> str:
    """Trace evolution links (git mining inferred; ADR/contract trusted).

    Requires index.git_mining: true and index rebuild.
    """
    try:
        manifest, _ = _load_or_error(rebuild_if_missing)
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )
    result = compute_evolution_trace(manifest, contract_id=contract_id, symbol=symbol)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def index_status(deep: bool = False) -> str:
    """Call first: index health before fetch_hits.

    Check recommend_rebuild, generated_at_age_hours, gaps_by_prefix,
    openapi_spec_count (0 with openapi on → collect/discover specs), missing_chunks_count.
    embedding_status is "disabled" when index.embeddings is off.
    deep=true adds stale_count (slower).
    Includes index_policy (mode/include/exclude/stats from last build when available).
    """
    return json.dumps(
        compute_index_status(_workspace(), deep=deep), ensure_ascii=False, indent=2
    )


@mcp.tool()
def explain_index_path(path: str) -> str:
    """Explain whether a workspace-relative path would be indexed and why.

    Uses the active index security policy: allowlist/denylist include/exclude,
    then .contractmeshignore + engine defaults. Does not rebuild the index.
    """
    from contractmesh.engine.index_policy import load_index_policy

    policy = load_index_policy(_workspace())
    return json.dumps(policy.explain(path).as_dict(), ensure_ascii=False, indent=2)


def _run_pr_impact(
    *,
    base: str | None,
    head: str,
    include_worktree: bool,
    rebuild_if_missing: bool,
) -> str:
    try:
        manifest, local_by_id = _load_or_error(rebuild_if_missing)
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )

    result, message = compute_pr_impact(
        _workspace(),
        manifest,
        local_by_id,
        base=base,
        head=head,
        include_worktree=include_worktree,
    )
    if message:
        return json.dumps({"error": "git_error", "message": message, **result}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def pr_impact(
    base: str = "main",
    head: str = "HEAD",
    include_worktree: bool = False,
    rebuild_if_missing: bool = False,
) -> str:
    """PR impact: map git diff to contracts, ADRs, anchors, tests, gaps and stale docs.

    Read-only git. Official tool for pre-PR / review workflows.
    Example: pr_impact(base="main", head="HEAD")

    Returns changed_files, contracts, adrs, code_anchors, test_anchors,
    known_gaps, suggested_test_commands, docs_possibly_stale and provenance.
    """
    return _run_pr_impact(
        base=base,
        head=head,
        include_worktree=include_worktree,
        rebuild_if_missing=rebuild_if_missing,
    )


@mcp.tool()
def branch_context(
    base: str | None = None,
    include_uncommitted: bool = True,
    rebuild_if_missing: bool = False,
) -> str:
    """Current branch, changed files and related contracts before commit/PR.

    Combines uncommitted worktree changes with diff against base (default main/master).
    """
    try:
        manifest, local_by_id = _load_or_error(rebuild_if_missing)
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )

    result, message = compute_branch_context(
        _workspace(),
        manifest,
        local_by_id,
        base=base,
        include_uncommitted=include_uncommitted,
    )
    if message:
        return json.dumps({"error": "git_error", "message": message}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def suggest_tests_for_diff(
    base: str | None = None,
    head: str = "HEAD",
    include_worktree: bool = True,
    limit: int = 12,
    rebuild_if_missing: bool = False,
) -> str:
    """Suggest indexed tests for files changed in git diff or worktree.

    Returns related test anchors and example commands (mvn test / npm build).
    """
    try:
        manifest, local_by_id = _load_or_error(rebuild_if_missing)
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )

    result, message = compute_suggest_tests_for_diff(
        _workspace(),
        manifest,
        local_by_id,
        base=base,
        head=head,
        include_worktree=include_worktree,
        limit=limit,
    )
    if message:
        return json.dumps({"error": "git_error", "message": message, **result}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def documentation_impact(
    base: str | None = None,
    head: str = "HEAD",
    include_worktree: bool = True,
    rebuild_if_missing: bool = False,
) -> str:
    """Evidence-based documentation review targets for a git diff or worktree.

    States: none (empty documents), possible (advisory), confirmed (soft-block candidate).
    Never marks confirmed solely because code changed and a linked doc did not.
    Prefer this over docs_drift_check (deprecated; replacement=documentation_impact).
    """
    try:
        manifest, _ = _load_or_error(rebuild_if_missing)
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )

    result, message = compute_documentation_impact(
        _workspace(),
        manifest,
        base=base,
        head=head,
        include_worktree=include_worktree,
    )
    if message:
        return json.dumps({"error": "git_error", "message": message, **result}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def docs_drift_check(
    base: str | None = None,
    head: str = "HEAD",
    include_worktree: bool = True,
    rebuild_if_missing: bool = False,
) -> str:
    """Deprecated alias of documentation_impact.

    Response always includes:
      deprecated: true
      replacement: documentation_impact
      replacement_cli: contractmesh docs impact
    Prefer documentation_impact.
    """
    try:
        manifest, _ = _load_or_error(rebuild_if_missing)
    except IndexNotFoundError as e:
        return json.dumps(
            {"error": "index_not_found", "message": str(e), "hint": e.hint},
            ensure_ascii=False,
        )

    result, message = compute_docs_drift_check(
        _workspace(),
        manifest,
        base=base,
        head=head,
        include_worktree=include_worktree,
    )
    if message:
        return json.dumps({"error": "git_error", "message": message, **result}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
