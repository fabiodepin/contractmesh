#!/usr/bin/env python3
"""Shared workspace knowledge index: search, chunks, gaps, status."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .build_contract_crosslinks import (
    CROSSLINK_SOURCE_KINDS,
    anchor_type_priority,
    build_related_anchors_for_hit,
    rank_code_anchor_ids,
)
from .chunk_ids import parse_chunk_id
from .trust_metadata import trust_rank

GAP_ID_RE = re.compile(r"\b[A-Z]{2,5}(?:-[A-Z0-9]+){1,5}-[0-9]{2,}\b")
PASCAL_TOKEN_RE = re.compile(r"^[A-Z][a-zA-Z0-9]+$")
from .workspace_paths import INDEX_BUILD_HINT, require_workspace, tool_root, workspace_layout
DEFAULT_MAX_CHARS = 8000
FETCH_HITS_DEFAULT_LIMIT = 3
FETCH_HITS_DEFAULT_MAX_CHARS_PER_CHUNK = 4000
FETCH_HITS_DEFAULT_MAX_RELATED_ANCHORS = 2
FETCH_HITS_DEFAULT_MAX_TOTAL_CHARS = 12000
INDEX_REBUILD_AGE_HOURS = 48
SYMBOL_EXACT_BOOST = 80
SYMBOL_PARTIAL_BOOST = 50
TRUNCATION_MAX_TOTAL_CHARS = "max_total_chars"
TRUNCATION_MAX_CHARS_PER_CHUNK = "max_chars_per_chunk"
TRUNCATION_LIMIT = "limit"
GAP_PREFIX_RE = re.compile(r"^([A-Z]{2,5}-[A-Z0-9]+)")
# Soft relative cutoff for impact seed hits (keep near-top matches only).
IMPACT_SEED_SCORE_RATIO = 0.82
IMPACT_SEED_SCORE_DELTA = 8
# Expand related_contracts only from the strongest seed contract(s).
IMPACT_RELATED_PRIMARY_LIMIT = 1
IMPACT_RELATED_MAX = 3
# Token-only test matches need stronger signal than a single stopword-ish hit.
IMPACT_TEST_MIN_TOKEN_SCORE = 6
IMPACT_ANCHOR_MAX = 12
IMPACT_ANCHOR_TYPE_SOFT_CAPS = {
    "entity": 2,
    "multitenancy": 2,
    "config": 1,
    "yaml_block": 1,
}
QUERY_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "for",
        "in",
        "on",
        "by",
        "if",
        "what",
        "when",
        "where",
        "how",
        "does",
        "do",
        "is",
        "are",
        "be",
        "with",
        "from",
        "this",
        "that",
        "these",
        "those",
        "into",
        "over",
        "under",
        "vs",
        "versus",
        "about",
        "before",
        "after",
        "need",
        "needs",
        "change",
        "changes",
        "changing",
        "modify",
        "modifying",
        "rule",
        "rules",
        "behavior",
        "behaviour",
    }
)


class IndexNotFoundError(FileNotFoundError):
    def __init__(self, workspace: Path) -> None:
        super().__init__(f"search index not found under {workspace}")
        self.workspace = workspace
        self.hint = INDEX_BUILD_HINT


@dataclass
class SearchHit:
    score: int
    doc_id: str
    repo: str
    path: str
    kind: str | None
    domain: str | None
    title: str
    heading: str | None
    known_gap_ids: list[str]
    snippet: str
    top_chunk_ids: list[str]
    links: dict[str, Any] = field(default_factory=dict)
    stale: bool = False
    chunks_missing: bool = False
    symbol: str | None = None
    anchor_type: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    related_anchors: list[dict[str, Any]] = field(default_factory=list)
    related_anchor_count: int = 0
    owner: dict[str, Any] = field(default_factory=dict)
    external_id: str | None = None
    status: str | None = None
    source_type: str | None = None
    trust_level: str | None = None


def get_workspace_root() -> Path:
    return require_workspace()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return f"sha256:{h.hexdigest()}"


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def tokenize_query(query: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9_\-]*", query.lower())


def significant_query_tokens(query: str | list[str]) -> list[str]:
    tokens = tokenize_query(query) if isinstance(query, str) else [t.lower() for t in query]
    return [t for t in tokens if t not in QUERY_STOPWORDS and len(t) > 1]


def _doc_text_blob(doc: dict) -> str:
    return " ".join(
        [
            str(doc.get("title") or ""),
            " ".join(doc.get("keywords") or []),
            " ".join(doc.get("headings") or []),
            str(doc.get("path") or ""),
            str(doc.get("symbol") or ""),
            str(doc.get("external_id") or ""),
        ]
    ).lower()


def _token_idf_weights(documents: list[dict], tokens: list[str]) -> dict[str, float]:
    """Soft IDF so rare query tokens outrank workspace-wide vocabulary."""
    if not tokens:
        return {}
    n = max(len(documents), 1)
    df = {t: 0 for t in tokens}
    for doc in documents:
        blob = _doc_text_blob(doc)
        for tok in tokens:
            if tok in blob:
                df[tok] += 1
    return {tok: 1.0 + math.log((n + 1) / (df[tok] + 1)) for tok in tokens}


def _filter_hits_by_relative_score(hits: list[SearchHit]) -> list[SearchHit]:
    if not hits:
        return []
    top = hits[0].score
    floor = max(int(top * IMPACT_SEED_SCORE_RATIO), top - IMPACT_SEED_SCORE_DELTA)
    kept = [h for h in hits if h.score >= floor]
    return kept or hits[:1]


def normalize_gap_id(gap: str) -> str:
    return gap.strip().upper()


def normalize_repo_kind_filters(
    repo: str | list[str] | None,
    kind: str | list[str] | None,
) -> tuple[list[str], list[str]]:
    def to_list(value: str | list[str] | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.lower()]
        return [v.lower() for v in value if v]

    return to_list(repo), to_list(kind)


def resolve_symbol_exact(query: str, symbol: str | None) -> str | None:
    if symbol and symbol.strip():
        return symbol.strip()
    q = query.strip()
    if not q:
        return None
    parts = q.split()
    if len(parts) == 1 and PASCAL_TOKEN_RE.match(parts[0]):
        return parts[0]
    return None


def is_symbol_partial_match(query_symbol: str, doc_symbol: str) -> bool:
    if not query_symbol or not doc_symbol or query_symbol == doc_symbol:
        return False
    if doc_symbol.startswith(query_symbol) and doc_symbol.endswith("Impl"):
        return True
    return False


def resolve_gap_exact(query: str, gap: str | None) -> str | None:
    if gap:
        return normalize_gap_id(gap)
    q = query.strip()
    if not q:
        return None
    gm = GAP_ID_RE.search(q)
    if gm and gm.group(0) == q:
        return gm.group(0)
    return None


CONTEXT_RICH_KINDS = frozenset({"contract", "integrations", "architecture"})


def cross_repo_keyword_boost(doc: dict, tokens: list[str]) -> int:
    """Small generic boost when the query names a repo and the doc is context-rich."""
    if not tokens:
        return 0
    repo = doc.get("repo", "").lower()
    repo_parts = {p for p in re.split(r"[^a-z0-9]+", repo) if p}
    token_set = {t.lower() for t in tokens}
    if not (repo in token_set or repo_parts & token_set):
        return 0
    boost = 0
    if doc.get("kind", "").lower() in CONTEXT_RICH_KINDS:
        boost += 3
    return boost


def score_document(
    doc: dict,
    tokens: list[str],
    gap_exact: str | None,
    symbol_exact: str | None,
    token_weights: dict[str, float] | None = None,
) -> int:
    gaps = doc.get("known_gap_ids", [])
    gap_match = bool(gap_exact and gap_exact in gaps)
    doc_symbol = doc.get("symbol") or ""

    if not tokens and not gap_exact and not symbol_exact:
        return 0

    content = 0
    if symbol_exact and doc_symbol:
        if doc_symbol == symbol_exact:
            content += SYMBOL_EXACT_BOOST
        elif is_symbol_partial_match(symbol_exact, doc_symbol):
            content += SYMBOL_PARTIAL_BOOST

    if gap_match:
        content += 50
        if doc.get("kind") in (
            "contract",
            "request_flow",
            "frontend_contract",
            "backend_contract",
        ):
            content += 12

    if not tokens and gap_exact and not gap_match and not symbol_exact:
        return 0
    if not tokens and symbol_exact and content == 0:
        return 0

    title_l = doc.get("title", "").lower()
    keywords_l = [k.lower() for k in doc.get("keywords", [])]
    headings_l = [h.lower() for h in doc.get("headings", [])]
    symbol_l = doc_symbol.lower()
    path_l = doc.get("path", "").lower()
    weights = token_weights or {}

    for tok in tokens:
        tok_l = tok.lower()
        weight = weights.get(tok, 1.0)
        contrib = 0
        if doc_symbol and (tok == symbol_l or tok_l == symbol_l):
            contrib += 5
        if tok in title_l or any(tok == k for k in keywords_l):
            contrib += 3
        elif any(tok in k for k in keywords_l):
            contrib += 2
        elif any(tok in h for h in headings_l):
            contrib += 1
        elif tok_l in path_l:
            contrib += 1
        if any(tok in g.lower() for g in gaps):
            contrib += 5
        if contrib:
            content += max(1, int(round(contrib * weight)))

    # Prefer docs whose titles cover multiple query tokens (reduces single-token drift).
    if tokens:
        title_hits = sum(1 for tok in tokens if tok in title_l)
        if title_hits >= 2:
            content += 3 * (title_hits - 1)

    if content == 0:
        return 0
    trust_boost = trust_rank(str(doc.get("trust_level", "confirmed"))) // 10
    return content + doc.get("weight", 0) // 10 + cross_repo_keyword_boost(doc, tokens) + trust_boost


def doc_passes_filters(
    doc: dict,
    repo_filters: list[str],
    kind_filters: list[str],
) -> bool:
    if repo_filters:
        repo_l = doc.get("repo", "").lower()
        path_l = doc.get("path", "").lower()
        domain_l = (doc.get("domain") or "").lower()
        if not any(
            rf == repo_l or rf in path_l or (domain_l and rf in domain_l)
            for rf in repo_filters
        ):
            return False
    if kind_filters and doc.get("kind", "").lower() not in kind_filters:
        return False
    return True


def _iter_chunk_rows(
    workspace: Path, local_by_id: dict[str, dict], doc_id: str
) -> list[dict]:
    loc = local_by_id.get(doc_id)
    if not loc:
        return []
    chunk_path = loc.get("chunk_path")
    if not chunk_path:
        return []
    abs_chunk = workspace / chunk_path
    if not abs_chunk.is_file():
        return []
    rows: list[dict] = []
    with abs_chunk.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def best_chunks_for_doc(
    workspace: Path,
    local_by_id: dict[str, dict],
    doc_id: str,
    tokens: list[str],
    top_n: int = 3,
) -> tuple[list[str], str | None, str | None]:
    rows = _iter_chunk_rows(workspace, local_by_id, doc_id)
    if not rows:
        return [], None, None

    scored: list[tuple[int, dict]] = []
    for row in rows:
        text = row.get("text", "")
        low = text.lower()
        s = sum(1 for t in tokens if t in low) if tokens else 0
        if not tokens:
            s = 0
        scored.append((s, row))

    scored.sort(key=lambda x: (-x[0], x[1].get("chunk_id", "")))
    top = [r for _, r in scored[:top_n]]
    chunk_ids = [r["chunk_id"] for r in top if r.get("chunk_id")]
    best_row = scored[0][1] if scored else {}
    return (
        chunk_ids,
        best_row.get("heading"),
        best_row.get("title"),
    )


def read_snippet_from_chunks(
    workspace: Path, local_by_id: dict[str, dict], doc_id: str, tokens: list[str]
) -> tuple[str, bool]:
    chunk_ids, _, _ = best_chunks_for_doc(workspace, local_by_id, doc_id, tokens, top_n=1)
    if not chunk_ids:
        loc = local_by_id.get(doc_id)
        if not loc or not loc.get("chunk_path"):
            return "", True
        abs_chunk = workspace / loc["chunk_path"]
        if not abs_chunk.is_file():
            return "", True
        return "", True

    rows = _iter_chunk_rows(workspace, local_by_id, doc_id)
    best_text = ""
    best_score = -1
    for row in rows:
        if row.get("chunk_id") != chunk_ids[0]:
            continue
        text = row.get("text", "")
        low = text.lower()
        s = sum(1 for t in tokens if t in low) if tokens else 0
        if s >= best_score:
            best_score = s
            best_text = text
    if not best_text and rows:
        best_text = rows[0].get("text", "")

    if best_text:
        snippet = best_text.replace("\n", " ").strip()
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."
        return snippet, False
    return "", True


def read_snippet_from_file(path: Path, tokens: list[str], max_lines: int = 8) -> str:
    if not path.is_file():
        return ""
    lines: list[str] = []
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    lines.append(stripped)
    except OSError:
        return ""
    snippet = " ".join(lines).strip()
    if len(snippet) > 200:
        snippet = snippet[:197] + "..."
    return snippet


def truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    return text[: max_chars - 3] + "...", True


def source_path_for_doc(
    workspace: Path, local_by_id: dict[str, dict], doc: dict
) -> Path:
    doc_id = doc["id"]
    loc = local_by_id.get(doc_id, {})
    abs_path = Path(loc.get("absolute_path", workspace / doc["path"]))
    if not abs_path.is_file():
        abs_path = workspace / doc["path"]
    return abs_path


def is_doc_stale(
    workspace: Path, local_by_id: dict[str, dict], doc: dict
) -> bool:
    loc = local_by_id.get(doc["id"], {})
    stored_hash = loc.get("content_hash")
    if not stored_hash:
        return False
    abs_path = source_path_for_doc(workspace, local_by_id, doc)
    if not abs_path.is_file():
        return False
    return sha256_file(abs_path) != stored_hash


def manifest_paths(workspace: Path) -> tuple[Path, Path]:
    layout = workspace_layout(workspace)
    return layout.manifest_path, layout.local_index_path


def load_index(workspace: Path) -> tuple[dict, dict[str, dict]]:
    manifest_path, local_path = manifest_paths(workspace)
    if not manifest_path.is_file():
        raise IndexNotFoundError(workspace)
    manifest = load_json(manifest_path)
    local_by_id: dict[str, dict] = {}
    if local_path.is_file():
        local_index = load_json(local_path)
        local_by_id = {d["id"]: d for d in local_index.get("documents", [])}
    return manifest, local_by_id


def run_build(workspace: Path) -> None:
    from .workspace_manifest import load_workspace_manifest, repo_specs

    manifest = load_workspace_manifest(workspace)
    repos_csv = ",".join(repo_specs(manifest))
    subprocess.run(
        [
            sys.executable,
            "-m",
            "contractmesh.engine.build_search_index",
            str(workspace.resolve()),
            repos_csv,
        ],
        check=True,
    )


def search_documents(
    workspace: Path,
    manifest: dict,
    local_by_id: dict[str, dict],
    *,
    query: str = "",
    gap: str | None = None,
    symbol: str | None = None,
    repo: str | list[str] | None = None,
    kind: str | list[str] | None = None,
    limit: int = 10,
    check_stale: bool = True,
) -> tuple[list[SearchHit], str | None]:
    """Search: symbol exact > symbol partial > gap exact > keyword > filters."""
    tokens = tokenize_query(query)
    gap_exact = resolve_gap_exact(query, gap)
    symbol_exact = resolve_symbol_exact(query, symbol)
    repo_filters, kind_filters = normalize_repo_kind_filters(repo, kind)

    if not tokens and not gap_exact and not symbol_exact:
        return [], "query, gap, or symbol required"

    candidates = [
        doc
        for doc in manifest.get("documents", [])
        if doc_passes_filters(doc, repo_filters, kind_filters)
    ]
    token_weights = _token_idf_weights(candidates, tokens) if tokens else {}

    results: list[tuple[int, dict]] = []
    for doc in candidates:
        sc = score_document(doc, tokens, gap_exact, symbol_exact, token_weights)
        if sc <= 0:
            continue
        results.append((sc, doc))

    results.sort(key=lambda x: (-x[0], x[1].get("path", "")))
    results = results[:limit]

    by_id = {d["id"]: d for d in manifest.get("documents", [])}

    hits: list[SearchHit] = []
    for sc, doc in results:
        doc_id = doc["id"]
        abs_path = source_path_for_doc(workspace, local_by_id, doc)
        stale = is_doc_stale(workspace, local_by_id, doc) if check_stale else False

        snippet, chunks_missing = read_snippet_from_chunks(
            workspace, local_by_id, doc_id, tokens
        )
        if chunks_missing and not snippet:
            snippet = read_snippet_from_file(abs_path, tokens)

        top_chunk_ids, chunk_heading, chunk_title = best_chunks_for_doc(
            workspace, local_by_id, doc_id, tokens, top_n=3
        )

        related_anchor_count = 0
        related_anchors: list[dict[str, Any]] = []
        if doc.get("kind") in CROSSLINK_SOURCE_KINDS and doc.get("code_anchors"):
            related_anchor_count, related_anchors = build_related_anchors_for_hit(
                doc, by_id
            )

        hits.append(
            SearchHit(
                score=sc,
                doc_id=doc_id,
                repo=doc.get("repo", ""),
                path=doc.get("path", ""),
                kind=doc.get("kind"),
                domain=doc.get("domain"),
                title=chunk_title or doc.get("title", ""),
                heading=chunk_heading,
                known_gap_ids=list(doc.get("known_gap_ids", [])),
                snippet=snippet,
                top_chunk_ids=top_chunk_ids,
                links=dict(doc.get("links", {})),
                stale=stale,
                chunks_missing=chunks_missing,
                symbol=doc.get("symbol"),
                anchor_type=doc.get("anchor_type"),
                line_start=doc.get("line_start"),
                line_end=doc.get("line_end"),
                related_anchors=related_anchors,
                related_anchor_count=related_anchor_count,
                owner=dict(doc.get("owner") or {}),
                external_id=doc.get("external_id"),
                status=doc.get("status"),
                source_type=doc.get("source_type"),
                trust_level=doc.get("trust_level"),
            )
        )

    return hits, None


def gap_id_prefix(gap_id: str) -> str:
    m = GAP_PREFIX_RE.match(gap_id.upper())
    return m.group(1) if m else gap_id.upper()


def collect_gaps_stats(manifest: dict) -> tuple[int, dict[str, int]]:
    unique: set[str] = set()
    by_prefix: dict[str, int] = {}
    for doc in manifest.get("documents", []):
        for gid in doc.get("known_gap_ids", []):
            unique.add(gid)
            prefix = gap_id_prefix(gid)
            by_prefix[prefix] = by_prefix.get(prefix, 0) + 1
    return len(unique), dict(sorted(by_prefix.items()))


def count_openapi_specs(manifest: dict) -> int:
    return sum(1 for d in manifest.get("documents", []) if d.get("kind") == "openapi_spec")


def parse_generated_at_age_hours(generated_at: str | None) -> float | None:
    if not generated_at:
        return None
    try:
        ts = generated_at.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return round(delta.total_seconds() / 3600, 2)
    except (ValueError, TypeError):
        return None


def recommend_index_rebuild(
    *,
    age_hours: float | None,
    missing_chunks: int,
    stale_count: int = 0,
) -> bool:
    if missing_chunks > 0 or stale_count > 0:
        return True
    if age_hours is not None and age_hours > INDEX_REBUILD_AGE_HOURS:
        return True
    return False


def _load_chunk_payload(
    workspace: Path,
    local_by_id: dict[str, dict],
    manifest: dict,
    chunk_id: str,
    max_chars: int,
) -> tuple[dict[str, Any] | None, int, bool, str | None]:
    """Return chunk dict, chars charged, truncated, per-chunk truncation_reason."""
    if max_chars <= 0:
        return None, 0, False, None
    row = read_chunk_by_id(
        workspace,
        local_by_id,
        chunk_id,
        manifest=manifest,
        max_chars=max_chars,
    )
    if not row:
        return None, 0, False, None
    text = row.get("text", "")
    charged = len(text)
    truncated = bool(row.get("truncated"))
    reason = TRUNCATION_MAX_CHARS_PER_CHUNK if truncated else None
    chunk_out = {
        "chunk_id": row.get("chunk_id", chunk_id),
        "text": text,
        "truncated": truncated,
    }
    if truncated and reason:
        chunk_out["truncation_reason"] = reason
    return chunk_out, charged, truncated, reason


def fetch_hits(
    workspace: Path,
    manifest: dict,
    local_by_id: dict[str, dict],
    *,
    query: str = "",
    gap: str | None = None,
    symbol: str | None = None,
    repo: str | list[str] | None = None,
    kind: str | list[str] | None = None,
    limit: int = FETCH_HITS_DEFAULT_LIMIT,
    max_chars_per_chunk: int = FETCH_HITS_DEFAULT_MAX_CHARS_PER_CHUNK,
    include_main_chunk: bool = True,
    include_related_anchors: bool = True,
    max_related_anchors_per_hit: int = FETCH_HITS_DEFAULT_MAX_RELATED_ANCHORS,
    max_total_chars: int = FETCH_HITS_DEFAULT_MAX_TOTAL_CHARS,
) -> tuple[dict[str, Any], str | None]:
    """Search and return hit metadata with chunk text under char budgets."""
    hits, message = search_documents(
        workspace,
        manifest,
        local_by_id,
        query=query,
        gap=gap,
        symbol=symbol,
        repo=repo,
        kind=kind,
        limit=limit,
        check_stale=False,
    )
    if message:
        return {}, message

    total_chars = 0
    out_hits: list[dict[str, Any]] = []
    response_truncated = False
    truncation_reasons: list[str] = []

    def budget_left() -> int:
        return max(0, max_total_chars - total_chars)

    def note_truncation(reason: str) -> None:
        nonlocal response_truncated
        response_truncated = True
        if reason not in truncation_reasons:
            truncation_reasons.append(reason)

    for hit in hits:
        if budget_left() <= 0:
            note_truncation(TRUNCATION_MAX_TOTAL_CHARS)
            break

        hit_out: dict[str, Any] = {
            "doc_id": hit.doc_id,
            "path": hit.path,
            "kind": hit.kind,
            "score": hit.score,
            "title": hit.title,
            "repo": hit.repo,
        }
        if hit.domain:
            hit_out["domain"] = hit.domain
        if hit.known_gap_ids:
            hit_out["known_gap_ids"] = hit.known_gap_ids
        if hit.owner:
            hit_out["owner"] = hit.owner
        if hit.external_id:
            hit_out["external_id"] = hit.external_id
        if hit.status:
            hit_out["status"] = hit.status
        doc_meta = next((d for d in manifest.get("documents", []) if d.get("id") == hit.doc_id), {})
        if doc_meta.get("trust_level"):
            hit_out["trust_level"] = doc_meta["trust_level"]
        if doc_meta.get("source_type"):
            hit_out["source_type"] = doc_meta["source_type"]

        if include_main_chunk and hit.top_chunk_ids:
            chunk_id = hit.top_chunk_ids[0]
            cap = min(max_chars_per_chunk, budget_left())
            chunk_payload, charged, t_chunk, t_reason = _load_chunk_payload(
                workspace, local_by_id, manifest, chunk_id, cap
            )
            if chunk_payload:
                hit_out["chunk"] = chunk_payload
                total_chars += charged
                if t_chunk and t_reason:
                    note_truncation(t_reason)
            if budget_left() <= 0:
                note_truncation(TRUNCATION_MAX_TOTAL_CHARS)

        anchor_items: list[dict[str, Any]] = []
        if include_related_anchors and hit.related_anchors and budget_left() > 0:
            for anchor in hit.related_anchors[:max_related_anchors_per_hit]:
                if budget_left() <= 0:
                    note_truncation(TRUNCATION_MAX_TOTAL_CHARS)
                    break
                anchor_out: dict[str, Any] = {
                    "symbol": anchor.get("symbol"),
                    "path": anchor.get("path"),
                    "anchor_type": anchor.get("anchor_type"),
                }
                if anchor.get("line_start") is not None:
                    anchor_out["line_start"] = anchor["line_start"]
                if anchor.get("line_end") is not None:
                    anchor_out["line_end"] = anchor["line_end"]
                top_ids = anchor.get("top_chunk_ids") or []
                if top_ids:
                    cap = min(max_chars_per_chunk, budget_left())
                    chunk_payload, charged, t_chunk, t_reason = _load_chunk_payload(
                        workspace,
                        local_by_id,
                        manifest,
                        top_ids[0],
                        cap,
                    )
                    if chunk_payload:
                        anchor_out["chunk"] = chunk_payload
                        total_chars += charged
                        if t_chunk and t_reason:
                            note_truncation(t_reason)
                anchor_items.append(anchor_out)
                if budget_left() <= 0:
                    note_truncation(TRUNCATION_MAX_TOTAL_CHARS)
                    break

        if anchor_items:
            hit_out["related_anchors"] = anchor_items
            if hit.related_anchor_count > len(anchor_items):
                hit_out["related_anchor_count"] = hit.related_anchor_count

        out_hits.append(hit_out)
        if budget_left() <= 0:
            break

    result: dict[str, Any] = {
        "hits": out_hits,
        "count": len(out_hits),
        "limits": {
            "limit": limit,
            "max_chars_per_chunk": max_chars_per_chunk,
            "max_related_anchors_per_hit": max_related_anchors_per_hit,
            "max_total_chars": max_total_chars,
            "include_main_chunk": include_main_chunk,
            "include_related_anchors": include_related_anchors,
        },
        "chars_used": total_chars,
        "truncated": response_truncated,
    }
    if response_truncated and truncation_reasons:
        result["truncation_reason"] = truncation_reasons[0]

    return result, None


def search_hit_to_dict(hit: SearchHit) -> dict[str, Any]:
    out: dict[str, Any] = {
        "score": hit.score,
        "doc_id": hit.doc_id,
        "repo": hit.repo,
        "path": hit.path,
        "kind": hit.kind,
        "domain": hit.domain,
        "title": hit.title,
        "heading": hit.heading,
        "known_gap_ids": hit.known_gap_ids,
        "snippet": hit.snippet,
        "top_chunk_ids": hit.top_chunk_ids,
        "links": hit.links,
    }
    if hit.symbol:
        out["symbol"] = hit.symbol
    if hit.anchor_type:
        out["anchor_type"] = hit.anchor_type
    if hit.line_start is not None:
        out["line_start"] = hit.line_start
    if hit.line_end is not None:
        out["line_end"] = hit.line_end
    if hit.related_anchor_count > 0:
        out["related_anchor_count"] = hit.related_anchor_count
    if hit.related_anchors:
        out["related_anchors"] = hit.related_anchors
    if hit.owner:
        out["owner"] = hit.owner
    if hit.external_id:
        out["external_id"] = hit.external_id
    if hit.status:
        out["status"] = hit.status
    if hit.source_type:
        out["source_type"] = hit.source_type
    if hit.trust_level:
        out["trust_level"] = hit.trust_level
    return out


def doc_path_from_manifest(manifest: dict, doc_id: str) -> str | None:
    for doc in manifest.get("documents", []):
        if doc.get("id") == doc_id:
            return doc.get("path")
    return None


def read_chunk_by_id(
    workspace: Path,
    local_by_id: dict[str, dict],
    chunk_id: str,
    *,
    manifest: dict | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict[str, Any] | None:
    doc_id, _chunk_index = parse_chunk_id(chunk_id)
    rel_path = doc_path_from_manifest(manifest, doc_id) if manifest else None
    for row in _iter_chunk_rows(workspace, local_by_id, doc_id):
        if row.get("chunk_id") == chunk_id:
            text = row.get("text", "")
            truncated, was_truncated = truncate_text(text, max_chars)
            out = dict(row)
            out["text"] = truncated
            out["truncated"] = was_truncated
            out["path"] = rel_path
            return out
    return None


def read_doc_chunks(
    workspace: Path,
    local_by_id: dict[str, dict],
    doc_id: str,
    *,
    manifest: dict | None = None,
    max_chunks: int = 5,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[dict[str, Any]] | None:
    rows = _iter_chunk_rows(workspace, local_by_id, doc_id)
    if not rows and doc_id not in local_by_id:
        return None

    path = doc_path_from_manifest(manifest, doc_id) if manifest else None
    out: list[dict[str, Any]] = []
    total_chars = 0
    for row in rows[:max_chunks]:
        text = row.get("text", "")
        remaining = max_chars - total_chars
        if remaining <= 0:
            break
        piece, truncated = truncate_text(text, remaining)
        total_chars += len(piece)
        item = {
            "chunk_id": row.get("chunk_id"),
            "doc_id": row.get("doc_id"),
            "title": row.get("title"),
            "heading": row.get("heading"),
            "text": piece,
            "truncated": truncated,
            "path": path,
        }
        out.append(item)
        if truncated:
            break
    return out


def list_known_gaps(
    manifest: dict,
    *,
    repo: str | list[str] | None = None,
    prefix: str | None = None,
    gap_id: str | None = None,
) -> dict[str, Any]:
    repo_filters, _ = normalize_repo_kind_filters(repo, None)
    prefix_u = prefix.strip().upper() if prefix else None
    gap_exact = normalize_gap_id(gap_id) if gap_id else None

    gap_to_docs: dict[str, list[dict[str, str]]] = {}

    for doc in manifest.get("documents", []):
        if not doc_passes_filters(doc, repo_filters, []):
            continue
        for gid in doc.get("known_gap_ids", []):
            if prefix_u and not gid.upper().startswith(prefix_u):
                continue
            if gap_exact and gid != gap_exact:
                continue
            gap_to_docs.setdefault(gid, []).append(
                {"doc_id": doc["id"], "path": doc.get("path", ""), "repo": doc.get("repo", "")}
            )

    if gap_exact:
        return {
            "gap_id": gap_exact,
            "documents": gap_to_docs.get(gap_exact, []),
        }

    gaps_sorted = sorted(gap_to_docs.keys())
    return {
        "gaps": [
            {"gap_id": g, "document_count": len(gap_to_docs[g]), "documents": gap_to_docs[g]}
            for g in gaps_sorted
        ],
        "total": len(gaps_sorted),
    }


def _doc_ref(doc: dict) -> dict[str, Any]:
    out: dict[str, Any] = {
        "doc_id": doc.get("id"),
        "repo": doc.get("repo", ""),
        "path": doc.get("path", ""),
        "kind": doc.get("kind"),
        "title": doc.get("title", ""),
    }
    for key in ("symbol", "anchor_type", "line_start", "line_end"):
        if doc.get(key) is not None:
            out[key] = doc[key]
    for key in ("owner", "external_id", "status"):
        if doc.get(key):
            out[key] = doc[key]
    for key in ("source_type", "trust_level"):
        if doc.get(key):
            out[key] = doc[key]
    if doc.get("known_gap_ids"):
        out["known_gap_ids"] = doc["known_gap_ids"]
    return out


def _owners_from_refs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    owners: list[dict[str, Any]] = []
    for item in items:
        owner = item.get("owner")
        if not isinstance(owner, dict):
            continue
        key = (
            str(owner.get("team", "")),
            str(owner.get("service", "")),
            str(owner.get("domain", "")),
            str(owner.get("contact", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        owners.append(owner)
    return owners


def _services_from_refs(items: list[dict[str, Any]]) -> list[str]:
    services: set[str] = set()
    workspace_repo = os.environ.get("WORKSPACE_REPO", "contractmesh")
    for item in items:
        owner = item.get("owner")
        if isinstance(owner, dict) and owner.get("service"):
            services.add(str(owner["service"]))
        elif item.get("repo"):
            repo = str(item["repo"])
            if repo != workspace_repo:
                services.add(repo)
    return sorted(services)


def _source_refs(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        path = str(item.get("path", ""))
        if not path or path in seen:
            continue
        seen.add(path)
        refs.append(
            {
                "path": path,
                "kind": str(item.get("kind", "")),
                "repo": str(item.get("repo", "")),
                "trust_level": str(item.get("trust_level", "")),
                "source_type": str(item.get("source_type", "")),
            }
        )
    return refs


def _dedupe_doc_refs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = str(item.get("doc_id") or item.get("path"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _chunk_text_for_doc(
    workspace: Path,
    local_by_id: dict[str, dict],
    doc_id: str,
    max_chars: int = 12000,
) -> str:
    parts: list[str] = []
    total = 0
    for row in _iter_chunk_rows(workspace, local_by_id, doc_id):
        text = row.get("text", "")
        if not text:
            continue
        remaining = max_chars - total
        if remaining <= 0:
            break
        piece = text[:remaining]
        parts.append(piece)
        total += len(piece)
    return "\n".join(parts)


def _symbols_from_seed_docs(seed_docs: list[dict]) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        if not value or value in seen:
            return
        seen.add(value)
        symbols.append(value)

    for doc in seed_docs:
        add(doc.get("symbol"))
        for aid in doc.get("code_anchors") or []:
            # anchor id shape: anchor:{repo}:{path}#{symbol}
            if "#" in aid:
                add(aid.rsplit("#", 1)[-1])
    return symbols


def _related_anchor_docs(
    manifest: dict,
    seed_docs: list[dict],
    *,
    limit: int = IMPACT_ANCHOR_MAX,
) -> list[dict]:
    """Collect ranked code anchors from seed docs, capped to keep impact graphs readable."""
    by_id = {d.get("id"): d for d in manifest.get("documents", [])}
    scored: list[tuple[int, int, int, str, dict]] = []
    seen: set[str] = set()
    for seed_idx, doc in enumerate(seed_docs):
        candidates: list[dict] = []
        if doc.get("kind") == "code_anchor":
            candidates.append(doc)
        preferred = list(doc.get("related_anchors") or [])
        anchor_ids = rank_code_anchor_ids(
            list(doc.get("code_anchors") or []),
            by_id,
            preferred_symbols=[str(s).split(".", 1)[0] for s in preferred],
        )
        for aid in anchor_ids:
            anchor = by_id.get(aid)
            if anchor:
                candidates.append(anchor)
        for cand in candidates:
            cid = str(cand.get("id") or "")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            scored.append(
                (
                    seed_idx,
                    -anchor_type_priority(cand.get("anchor_type")),
                    0 if cand.get("kind") == "code_anchor" else 1,
                    str(cand.get("symbol") or cand.get("path") or ""),
                    cand,
                )
            )
    scored.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    type_counts: dict[str, int] = {}
    out: list[dict] = []
    for _seed, _prio, _kind, _sym, cand in scored:
        atype = str(cand.get("anchor_type") or "")
        soft_cap = IMPACT_ANCHOR_TYPE_SOFT_CAPS.get(atype)
        if soft_cap is not None and type_counts.get(atype, 0) >= soft_cap:
            continue
        type_counts[atype] = type_counts.get(atype, 0) + 1
        out.append(_doc_ref(cand))
        if len(out) >= limit:
            break
    return out


def _expand_related_contract_docs(
    manifest: dict,
    seed_docs: list[dict],
    *,
    query_tokens: list[str] | None = None,
    primary_limit: int | None = None,
    related_limit: int | None = None,
) -> list[dict]:
    """Expand related_contracts from seed docs.

    When primary_limit/related_limit are set (impact_analysis), only expand from
    the strongest contract seeds and prefer related docs that still overlap the
    query. Callers that omit limits keep the previous "expand all" behavior.
    """
    by_external_id = {
        d.get("external_id"): d
        for d in manifest.get("documents", [])
        if d.get("external_id")
    }
    contract_seeds = [d for d in seed_docs if d.get("kind") == "contract"]
    if primary_limit is not None:
        contract_seeds = contract_seeds[: max(primary_limit, 0)]
    elif primary_limit is None and related_limit is None and query_tokens is None:
        contract_seeds = seed_docs

    sig_tokens = significant_query_tokens(query_tokens or [])
    token_weights = _token_idf_weights(manifest.get("documents", []), sig_tokens)
    out: list[dict] = []
    seen: set[str] = {d.get("id", "") for d in seed_docs}

    def take(related: dict, *, require_distinctive: bool) -> bool:
        doc_id = related.get("id", "")
        if not doc_id or doc_id in seen:
            return False
        if sig_tokens and not _related_passes_query_gate(
            related,
            sig_tokens,
            token_weights,
            require_distinctive=require_distinctive,
        ):
            return False
        seen.add(doc_id)
        out.append(related)
        return True

    # First hop from primary seed contract(s).
    for doc in contract_seeds:
        for external_id in doc.get("related_contracts") or []:
            related = by_external_id.get(external_id)
            if not related:
                continue
            # Distinctive overlap kills common-token cascades (mailbox via "email").
            if not take(related, require_distinctive=bool(sig_tokens)):
                continue
            if related_limit is not None and len(out) >= related_limit:
                return out

    # One controlled second hop from first-hop contracts that pass a distinctive gate.
    # Prefer stronger query overlap so auth companions beat weak multitenancy edges.
    # Children only need any significant-token overlap (parent already passed the gate).
    if related_limit is not None and len(out) < related_limit:
        ranked = sorted(token_weights.values()) if token_weights else []
        median = ranked[len(ranked) // 2] if ranked else 1.0

        def distinctive_overlap(doc: dict) -> int:
            blob = _doc_text_blob(doc)
            return sum(
                1
                for tok in sig_tokens
                if tok in blob and token_weights.get(tok, 1.0) >= median
            )

        first_hop = sorted(out, key=distinctive_overlap, reverse=True)
        for rel in first_hop:
            if distinctive_overlap(rel) <= 0 and sig_tokens:
                continue
            for external_id in rel.get("related_contracts") or []:
                related = by_external_id.get(external_id)
                if not related:
                    continue
                if not take(related, require_distinctive=False):
                    continue
                if len(out) >= related_limit:
                    return out
    return out


def _related_passes_query_gate(
    related: dict,
    sig_tokens: list[str],
    token_weights: dict[str, float],
    *,
    require_distinctive: bool,
) -> bool:
    if not sig_tokens:
        return True
    blob = _doc_text_blob(related)
    if not any(tok in blob for tok in sig_tokens):
        return False
    if not require_distinctive or not token_weights:
        return True
    ranked = sorted(token_weights.values())
    median = ranked[len(ranked) // 2]
    distinctive = [t for t in sig_tokens if token_weights.get(t, 1.0) >= median]
    if not distinctive:
        return True
    return any(tok in blob for tok in distinctive)


def _camel_case_parts(symbol: str) -> list[str]:
    return re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+", symbol)


def symbol_match_variants(symbol: str) -> list[str]:
    """Match AuthLoginService against AuthLoginIntegrationTest via shared stems."""
    raw = (symbol or "").strip()
    if not raw:
        return []
    variants: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        v = value.lower()
        if len(v) < 5 or v in seen:
            return
        seen.add(v)
        variants.append(v)

    add(raw)
    parts = _camel_case_parts(raw)
    for i in range(len(parts), 1, -1):
        add("".join(parts[:i]))
    # Drop ultra-generic trailing Service/Controller/Test stems alone.
    return variants


def _matching_test_docs(
    workspace: Path,
    manifest: dict,
    local_by_id: dict[str, dict],
    *,
    repo_filters: list[str],
    symbols: list[str],
    query_tokens: list[str],
    limit: int,
    min_token_score: int = 0,
    primary_symbols: list[str] | None = None,
    require_primary_symbol: bool = False,
) -> list[dict[str, Any]]:
    scored: list[tuple[int, dict]] = []
    primary = [s for s in (primary_symbols or []) if s]
    primary_variants = [v for sym in primary for v in symbol_match_variants(sym)]
    secondary = [s for s in symbols if s and s not in primary]
    secondary_l = [s.lower() for s in secondary]
    sig_tokens = significant_query_tokens(query_tokens)
    for doc in manifest.get("documents", []):
        if doc.get("kind") != "test_anchor":
            continue
        if not doc_passes_filters(doc, repo_filters, []):
            continue
        haystack = " ".join(
            [
                doc.get("symbol", ""),
                doc.get("title", ""),
                doc.get("path", ""),
                " ".join(doc.get("keywords", [])),
                _chunk_text_for_doc(workspace, local_by_id, doc["id"], max_chars=8000),
            ]
        ).lower()
        primary_score = 0
        for variant in primary_variants:
            if variant in haystack:
                # Longer shared stems are stronger (AuthLoginService > Auth).
                primary_score = max(primary_score, 12 + min(len(variant), 16))
        secondary_score = 0
        for sym in secondary_l:
            if sym and sym in haystack:
                secondary_score += 5
        token_score = 0
        for tok in sig_tokens:
            if tok in haystack:
                token_score += 2
        score = primary_score + secondary_score + token_score
        if score <= 0:
            continue
        if require_primary_symbol and primary_variants and primary_score <= 0:
            continue
        if primary_score <= 0 and secondary_score <= 0 and token_score < min_token_score:
            continue
        scored.append((score, doc))
    scored.sort(key=lambda item: (-item[0], item[1].get("path", "")))
    return [_doc_ref(doc) | {"score": score} for score, doc in scored[:limit]]


def related_tests(
    workspace: Path,
    manifest: dict,
    local_by_id: dict[str, dict],
    *,
    query: str = "",
    symbol: str | None = None,
    repo: str | list[str] | None = None,
    limit: int = 8,
) -> tuple[dict[str, Any], str | None]:
    """Find tests related to a contract, query, or code symbol."""
    repo_filters, _ = normalize_repo_kind_filters(repo, None)
    seed_hits, message = search_documents(
        workspace,
        manifest,
        local_by_id,
        query=query,
        symbol=symbol,
        repo=repo,
        kind=["contract", "integrations", "architecture", "code_anchor"],
        limit=8,
        check_stale=False,
    )
    if message:
        return {}, message

    seed_by_id = {h.doc_id: h for h in seed_hits}
    seed_docs = [
        d for d in manifest.get("documents", []) if d.get("id") in seed_by_id
    ]
    secondary_symbols = _symbols_from_seed_docs(seed_docs)
    primary_symbols = [symbol] if symbol else []
    symbols_considered = list(primary_symbols)
    for sym in secondary_symbols:
        if sym not in symbols_considered:
            symbols_considered.append(sym)
    tests = _matching_test_docs(
        workspace,
        manifest,
        local_by_id,
        repo_filters=repo_filters,
        symbols=secondary_symbols,
        query_tokens=tokenize_query(query),
        limit=limit,
        primary_symbols=primary_symbols,
        require_primary_symbol=bool(symbol),
    )

    seed_refs = [search_hit_to_dict(h) for h in seed_hits]
    owners = _owners_from_refs(seed_refs + tests)
    return {
        "query": query,
        "symbol": symbol,
        "seed_sources": seed_refs,
        "symbols_considered": symbols_considered,
        "related_tests": tests,
        "owners": owners,
        "services": _services_from_refs(seed_refs + tests),
        "count": len(tests),
        "provenance": "Derived from indexed contracts/code anchors and test anchors. Rebuild the index after adding tests.",
    }, None


def impact_analysis(
    workspace: Path,
    manifest: dict,
    local_by_id: dict[str, dict],
    *,
    query: str = "",
    gap: str | None = None,
    symbol: str | None = None,
    repo: str | list[str] | None = None,
    limit: int = 5,
) -> tuple[dict[str, Any], str | None]:
    """Collect likely change-impact evidence for a behavior/rule change."""
    hits, message = search_documents(
        workspace,
        manifest,
        local_by_id,
        query=query,
        gap=gap,
        symbol=symbol,
        repo=repo,
        kind=["contract", "integrations", "architecture", "adr", "known_gaps", "code_anchor"],
        limit=limit,
        check_stale=False,
    )
    if message:
        return {}, message

    kept_hits = _filter_hits_by_relative_score(hits)
    hit_score = {h.doc_id: h.score for h in kept_hits}
    hit_ids = set(hit_score)
    seed_docs = [d for d in manifest.get("documents", []) if d.get("id") in hit_ids]
    non_workspace_seed_docs = [
        d for d in seed_docs if d.get("repo") != os.environ.get("WORKSPACE_REPO", "contractmesh")
    ]
    if non_workspace_seed_docs:
        seed_docs = non_workspace_seed_docs
    seed_docs.sort(
        key=lambda d: (-hit_score.get(d.get("id", ""), 0), d.get("path", "")),
    )
    query_tokens = significant_query_tokens(query)
    primary_seed_docs = list(seed_docs)
    seed_docs.extend(
        _expand_related_contract_docs(
            manifest,
            seed_docs,
            query_tokens=query_tokens,
            primary_limit=IMPACT_RELATED_PRIMARY_LIMIT,
            related_limit=IMPACT_RELATED_MAX,
        )
    )
    contracts = [_doc_ref(d) for d in seed_docs if d.get("kind") == "contract"]
    adrs = [_doc_ref(d) for d in seed_docs if d.get("kind") == "adr"]
    context_docs = [
        _doc_ref(d)
        for d in seed_docs
        if d.get("kind") in ("integrations", "architecture")
    ]
    # Only dedicated gap docs here; contracts already expose known_gap_ids on their refs.
    gap_docs = [
        _doc_ref(d)
        for d in seed_docs
        if d.get("kind") == "known_gaps"
    ]
    anchors = _related_anchor_docs(manifest, seed_docs, limit=IMPACT_ANCHOR_MAX)
    # Prefer symbols from primary seeds (not cascade-related contracts) for test matching.
    secondary_symbols = _symbols_from_seed_docs(primary_seed_docs)
    primary_symbols = [symbol] if symbol else []
    if symbol and symbol not in secondary_symbols:
        secondary_symbols.insert(0, symbol)
    repo_filters, _ = normalize_repo_kind_filters(repo, None)
    tests = _matching_test_docs(
        workspace,
        manifest,
        local_by_id,
        repo_filters=repo_filters,
        symbols=secondary_symbols,
        query_tokens=query_tokens,
        limit=limit,
        min_token_score=IMPACT_TEST_MIN_TOKEN_SCORE,
        primary_symbols=primary_symbols,
        require_primary_symbol=bool(symbol),
    )
    all_refs = (
        _dedupe_doc_refs(contracts)
        + _dedupe_doc_refs(context_docs)
        + _dedupe_doc_refs(adrs)
        + anchors
        + tests
        + _dedupe_doc_refs(gap_docs)
    )
    seed_sources = [search_hit_to_dict(h) for h in kept_hits]

    return {
        "query": query,
        "gap": gap,
        "symbol": symbol,
        "summary": "Review these owners, contracts, ADRs, anchors, tests and known gaps before changing the rule.",
        "contracts": _dedupe_doc_refs(contracts),
        "context_docs": _dedupe_doc_refs(context_docs),
        "adrs": _dedupe_doc_refs(adrs),
        "owners": _owners_from_refs(all_refs + seed_sources),
        "services": _services_from_refs(all_refs + seed_sources),
        "code_anchors": anchors,
        "test_anchors": tests,
        "related_tests": tests,
        "known_gaps": _dedupe_doc_refs(gap_docs),
        "drift_findings": manifest.get("drift_findings") or [],
        "seed_sources": seed_sources,
        "provenance": {
            "sources_consulted": _source_refs(all_refs + seed_sources),
            "retrieval_strategy": (
                "contracts-first deterministic retrieval with trust ranking, "
                "soft IDF, relative seed cutoff, and primary-related expansion"
            ),
            "note": "Direct code reads may still be needed before editing.",
        },
    }, None


def orient_workspace(
    workspace: Path,
    manifest: dict,
    *,
    repo: str | list[str] | None = None,
) -> dict[str, Any]:
    """Summarize routes and controller/service/repository layers (inferred)."""
    repo_filters, _ = normalize_repo_kind_filters(repo, None)
    edges = manifest.get("structural_edges") or []
    if repo_filters:
        edges = [e for e in edges if e.get("repo", "").lower() in repo_filters]

    top_contracts = [
        _doc_ref(d)
        for d in manifest.get("documents", [])
        if d.get("kind") == "contract" and d.get("trust_level") == "confirmed"
    ][:8]

    return {
        "routes": [e for e in edges if e.get("edge_type") == "implements_route"][:40],
        "uses_service": [e for e in edges if e.get("edge_type") == "uses_service"][:40],
        "uses_repository": [e for e in edges if e.get("edge_type") == "uses_repository"][:40],
        "imports": [e for e in edges if e.get("edge_type") == "imports"][:40],
        "top_contracts": top_contracts,
        "structural_edge_count": len(edges),
        "trust_note": "Structural edges are inferred; contracts are confirmed.",
        "sources_consulted": [
            {
                "path": ".contractmesh/index/search-index.manifest.json",
                "kind": "structural_graph",
                "trust_level": "inferred",
            }
        ],
    }


def list_drift(manifest: dict) -> dict[str, Any]:
    findings = manifest.get("drift_findings") or []
    return {
        "findings": findings,
        "count": len(findings),
        "trust_note": "Drift findings are detected_mismatch; review before acting.",
    }


def evolution_trace(
    manifest: dict,
    *,
    contract_id: str | None = None,
    symbol: str | None = None,
) -> dict[str, Any]:
    links = manifest.get("evolution_links") or []
    needle = (contract_id or symbol or "").strip()
    if needle:
        links = [
            link
            for link in links
            if needle in {link.get("source"), link.get("target")}
        ]
    return {
        "query": {"contract_id": contract_id, "symbol": symbol},
        "links": links,
        "trusted_links": [
            l for l in links if l.get("trust_level") in ("confirmed", "accepted", "implementation")
        ],
        "inferred_links": [l for l in links if l.get("trust_level") == "inferred"],
        "count": len(links),
    }


def aggregate_embedding_status(
    manifest: dict,
    *,
    embeddings_enabled: bool | None = None,
) -> str:
    if embeddings_enabled is False:
        return "disabled"
    statuses: set[str] = set()
    for doc in manifest.get("documents", []):
        emb = doc.get("embedding") or {}
        st = emb.get("status") or "pending"
        statuses.add(st)
    if statuses == {"pending"}:
        return "pending"
    if "ready" in statuses and statuses <= {"ready", "pending"}:
        return "ready" if statuses == {"ready"} else "partial"
    if len(statuses) > 1:
        return "partial"
    return next(iter(statuses)) if statuses else "pending"


def openapi_status_hint(
    *,
    openapi_enabled: bool,
    openapi_spec_count: int,
) -> str | None:
    if not openapi_enabled:
        return (
            "OpenAPI indexing is off. Set index.openapi: true and place specs under "
            ".contractmesh/generated/openapi/ (or discoverable openapi/swagger files)."
        )
    if openapi_spec_count <= 0:
        return (
            "OpenAPI indexing is on but no specs were found. Run collect-openapi "
            "(docs/ai/openapi-sources.yaml) or add openapi.json/yaml under a repo."
        )
    return None


def embeddings_status_hint(*, embeddings_enabled: bool, embedding_status: str) -> str | None:
    if not embeddings_enabled:
        return (
            "Embeddings are off by design (deterministic retrieval first). "
            "Set index.embeddings: true when vector recall is implemented/enabled."
        )
    if embedding_status in ("pending", "partial"):
        return "Embeddings enabled but vectors are not fully ready yet."
    return None


def index_status(workspace: Path, *, deep: bool = False) -> dict[str, Any]:
    manifest_path, local_path = manifest_paths(workspace)
    out: dict[str, Any] = {
        "manifest_exists": manifest_path.is_file(),
        "index_build_hint": INDEX_BUILD_HINT,
    }

    if not manifest_path.is_file():
        out.update(
            {
                "generated_at": None,
                "workspace_mapping_version": None,
                "total_docs": 0,
                "total_chunks": 0,
                "embedding_status": None,
                "missing_chunks_count": 0,
                "stale_check": "skipped",
            }
        )
        return out

    manifest = load_json(manifest_path)
    local_by_id: dict[str, dict] = {}
    total_chunks = 0
    missing_chunks = 0
    code_anchor_count = 0
    test_anchor_count = 0
    code_anchor_by_repo: dict[str, int] = {}

    for doc in manifest.get("documents", []):
        if doc.get("kind") == "code_anchor":
            code_anchor_count += 1
            r = doc.get("repo", "")
            if r:
                code_anchor_by_repo[r] = code_anchor_by_repo.get(r, 0) + 1
        if doc.get("kind") == "test_anchor":
            test_anchor_count += 1

    if local_path.is_file():
        local_index = load_json(local_path)
        for d in local_index.get("documents", []):
            local_by_id[d["id"]] = d
            total_chunks += int(d.get("chunk_count", 0))
            cp = d.get("chunk_path")
            if cp and not (workspace / cp).is_file():
                missing_chunks += 1

    build_stats = manifest.get("build_stats") or {}
    generated_at = manifest.get("generated_at")
    age_hours = parse_generated_at_age_hours(generated_at)
    gaps_count, gaps_by_prefix = collect_gaps_stats(manifest)
    openapi_spec_count = count_openapi_specs(manifest)
    index_flags = build_stats.get("index_flags") or {}
    embeddings_enabled = bool(index_flags.get("embeddings"))
    openapi_enabled = bool(index_flags.get("openapi"))
    embedding_status = aggregate_embedding_status(
        manifest, embeddings_enabled=embeddings_enabled
    )
    contracts_with_anchors = build_stats.get(
        "contracts_with_code_anchors",
        sum(
            1
            for d in manifest.get("documents", [])
            if d.get("kind") in CROSSLINK_SOURCE_KINDS and d.get("code_anchors")
        ),
    )

    out.update(
        {
            "generated_at": generated_at,
            "generated_at_age_hours": age_hours,
            "workspace_mapping_version": manifest.get("workspace_mapping_version"),
            "total_docs": len(manifest.get("documents", [])),
            "total_chunks": total_chunks,
            "embedding_status": embedding_status,
            "embeddings_enabled": embeddings_enabled,
            "missing_chunks_count": missing_chunks,
            "code_anchor_count": code_anchor_count,
            "test_anchor_count": test_anchor_count,
            "code_anchor_by_repo": code_anchor_by_repo,
            "gaps_indexed_count": gaps_count,
            "gaps_by_prefix": gaps_by_prefix,
            "openapi_spec_count": openapi_spec_count,
            "openapi_enabled": openapi_enabled,
            "openapi_hint": openapi_status_hint(
                openapi_enabled=openapi_enabled,
                openapi_spec_count=openapi_spec_count,
            ),
            "embeddings_hint": embeddings_status_hint(
                embeddings_enabled=embeddings_enabled,
                embedding_status=embedding_status,
            ),
            "recommend_rebuild": recommend_index_rebuild(
                age_hours=age_hours,
                missing_chunks=missing_chunks,
            ),
            "contract_symbols_unresolved_total": build_stats.get(
                "contract_symbols_unresolved_total", 0
            ),
            "contract_symbols_unresolved_unique": build_stats.get(
                "contract_symbols_unresolved_unique", 0
            ),
            "contracts_with_code_anchors": contracts_with_anchors,
            "anchors_with_related_doc_ids": build_stats.get(
                "anchors_with_related_doc_ids",
                sum(
                    1
                    for d in manifest.get("documents", [])
                    if d.get("kind") == "code_anchor" and d.get("related_doc_ids")
                ),
            ),
            "crosslink_source_kinds": build_stats.get(
                "crosslink_source_kinds", sorted(CROSSLINK_SOURCE_KINDS)
            ),
            "index_flags": index_flags,
            "index_policy": build_stats.get("index_policy")
            or {
                "mode": index_flags.get("mode"),
                "include": index_flags.get("include") or [],
                "exclude": index_flags.get("exclude") or [],
            },
            "structural_edge_count": build_stats.get("structural_edge_count", len(manifest.get("structural_edges") or [])),
            "drift_finding_count": build_stats.get("drift_finding_count", len(manifest.get("drift_findings") or [])),
            "evolution_link_count": build_stats.get("evolution_link_count", len(manifest.get("evolution_links") or [])),
        }
    )

    stale_count = 0
    if deep:
        for doc in manifest.get("documents", []):
            if is_doc_stale(workspace, local_by_id, doc):
                stale_count += 1
        out["stale_count"] = stale_count
        out["stale_check"] = "deep"
        out["deep_checked_at"] = datetime.now(timezone.utc).isoformat()
    else:
        out["stale_check"] = "skipped"

    out["recommend_rebuild"] = recommend_index_rebuild(
        age_hours=age_hours,
        missing_chunks=missing_chunks,
        stale_count=stale_count,
    )

    if not out["manifest_exists"] or missing_chunks > 0:
        out["index_build_hint"] = INDEX_BUILD_HINT

    return out
