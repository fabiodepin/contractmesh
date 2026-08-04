#!/usr/bin/env python3
"""Cross-link CROSSLINK_SOURCE_KINDS docs to code_anchor entries in the search index."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CROSSLINK_SOURCE_KINDS = frozenset({"contract", "architecture", "integrations", "adr"})

RELATED_ANCHORS_SEARCH_LIMIT = 12

# Prefer behavioral entrypoints over data-model types in retrieval surfaces.
ANCHOR_TYPE_PRIORITY: dict[str, int] = {
    "controller": 100,
    "ts_page": 96,
    "service": 92,
    "service_impl": 90,
    "filter": 84,
    "ts_store": 82,
    "client": 78,
    "support": 72,
    "multitenancy": 58,
    "java_type": 40,
    "config": 36,
    "entity": 20,
    "yaml_block": 18,
}

EXCLUDED_SYMBOL_SUFFIXES = ("Payload", "Dto", "DTO")
TOKEN_STOPWORDS = frozenset(
    {
        "GET",
        "POST",
        "PUT",
        "DELETE",
        "PATCH",
        "HEAD",
        "JSON",
        "URL",
        "HTTP",
        "HTTPS",
        "API",
        "JWT",
        "SQL",
        "Authorization",
        "Bearer",
    }
)

BACKTICK_SYMBOL_RE = re.compile(r"`([A-Z][A-Za-z0-9]{2,})`")
PROSE_SYMBOL_RE = re.compile(
    r"\b([A-Z][a-zA-Z0-9]*(?:ServiceImpl|Service|Controller|Client|Filter|Config|Configuration|Utils|Resolver|Limiter|Guard))\b"
)
PASCAL_RE = re.compile(r"^[A-Z][a-zA-Z0-9]+$")


@dataclass
class CrosslinkStats:
    contracts_with_code_anchors: int = 0
    anchors_with_related_doc_ids: int = 0
    contract_symbols_unresolved_total: int = 0
    contract_symbols_unresolved_unique: int = 0
    # "repo:Symbol" keys that failed same-repo and any-repo lookup
    unresolved_symbols: list[str] | None = None


def should_link_symbol(name: str, *, from_prose: bool = False) -> bool:
    if not PASCAL_RE.match(name) or len(name) < 3:
        return False
    # Skip ALL_CAPS tokens (enums/HTTP verbs already covered, plus ACTIVE/BLOCKED/…)
    if name.isupper():
        return False
    if name in TOKEN_STOPWORDS:
        return False
    if any(name.endswith(suffix) for suffix in EXCLUDED_SYMBOL_SUFFIXES):
        return False
    if from_prose:
        return bool(PROSE_SYMBOL_RE.fullmatch(name))
    return True


def extract_symbols_from_text(text: str) -> list[str]:
    """Symbols in document order; backticks first, then prose (deduped)."""
    seen: set[str] = set()
    ordered: list[str] = []

    def add(sym: str, from_prose: bool = False) -> None:
        if sym in seen:
            return
        if not should_link_symbol(sym, from_prose=from_prose):
            return
        seen.add(sym)
        ordered.append(sym)

    for m in BACKTICK_SYMBOL_RE.finditer(text):
        add(m.group(1), from_prose=False)

    for m in PROSE_SYMBOL_RE.finditer(text):
        add(m.group(1), from_prose=True)

    return ordered


def build_anchor_registry(
    manifest_docs: list[dict],
) -> tuple[dict[tuple[str, str], list[str]], dict[str, dict]]:
    """Case-sensitive (repo, symbol) -> [anchor doc_id, ...]; doc_id -> manifest row."""
    by_repo_symbol: dict[tuple[str, str], list[str]] = {}
    by_id: dict[str, dict] = {}
    for doc in manifest_docs:
        by_id[doc["id"]] = doc
        if doc.get("kind") != "code_anchor":
            continue
        sym = doc.get("symbol")
        repo = doc.get("repo")
        if not sym or not repo:
            continue
        key = (repo, sym)
        if doc["id"] not in by_repo_symbol.setdefault(key, []):
            by_repo_symbol[key].append(doc["id"])
    return by_repo_symbol, by_id


def resolve_anchor_ids(
    repo: str,
    sym: str,
    by_repo_symbol: dict[tuple[str, str], list[str]],
) -> list[str]:
    """Exact case-sensitive lookup; Service -> ServiceImpl fallback when missing."""
    ids = list(by_repo_symbol.get((repo, sym), []))
    if ids:
        return ids
    if sym.endswith("Service") and not sym.endswith("Impl"):
        return list(by_repo_symbol.get((repo, f"{sym}Impl"), []))
    return []


def resolve_anchor_ids_any_repo(
    sym: str,
    by_repo_symbol: dict[tuple[str, str], list[str]],
) -> list[str]:
    ids: list[str] = []
    for (_repo, candidate), anchor_ids in by_repo_symbol.items():
        if candidate == sym or (
            sym.endswith("Service")
            and not sym.endswith("Impl")
            and candidate == f"{sym}Impl"
        ):
            ids.extend(anchor_ids)
    return ids


def normalize_anchor_symbol(value: str) -> str:
    """Allow ADR front matter to reference Symbol.method while anchors use Symbol."""
    return value.strip().split(".", 1)[0]


def preferred_symbols_from_doc(doc: dict) -> list[str]:
    """Front-matter related_anchors are explicit intent and should rank first."""
    preferred: list[str] = []
    seen: set[str] = set()
    for raw in doc.get("related_anchors") or []:
        sym = normalize_anchor_symbol(str(raw))
        if not sym or sym in seen:
            continue
        if not should_link_symbol(sym):
            continue
        seen.add(sym)
        preferred.append(sym)
    return preferred


def anchor_type_priority(anchor_type: str | None) -> int:
    if not anchor_type:
        return 10
    return ANCHOR_TYPE_PRIORITY.get(str(anchor_type), 10)


def rank_code_anchor_ids(
    anchor_ids: list[str],
    by_id: dict[str, dict],
    *,
    preferred_symbols: list[str] | None = None,
) -> list[str]:
    """Rank anchors: explicit related_anchors order, then behavioral types."""
    preferred = preferred_symbols or []
    preferred_rank = {sym: len(preferred) - idx for idx, sym in enumerate(preferred)}

    def sort_key(aid: str) -> tuple[int, int, str]:
        anchor = by_id.get(aid) or {}
        symbol = str(anchor.get("symbol") or "")
        return (
            preferred_rank.get(symbol, 0),
            anchor_type_priority(anchor.get("anchor_type")),
            symbol,
        )

    # Stable unique preserve-then-rank
    seen: set[str] = set()
    unique: list[str] = []
    for aid in anchor_ids:
        if not aid or aid in seen:
            continue
        seen.add(aid)
        unique.append(aid)
    return sorted(unique, key=sort_key, reverse=True)


def apply_contract_crosslinks(
    workspace: Path,
    manifest_docs: list[dict],
) -> CrosslinkStats:
    """
    Set code_anchors on source docs and related_doc_ids on code_anchor rows.
    Mutates manifest_docs in place.
    """
    stats = CrosslinkStats()
    unresolved_unique: set[str] = set()

    by_repo_symbol, by_id = build_anchor_registry(manifest_docs)

    for doc in manifest_docs:
        if doc.get("kind") == "code_anchor":
            doc["related_doc_ids"] = []

    for doc in manifest_docs:
        if doc.get("kind") not in CROSSLINK_SOURCE_KINDS:
            continue
        rel = doc.get("path", "")
        if not rel:
            continue
        abs_path = workspace / rel
        if not abs_path.is_file():
            continue

        text = abs_path.read_text(encoding="utf-8", errors="replace")
        preferred = preferred_symbols_from_doc(doc)
        body_symbols = extract_symbols_from_text(text)
        symbols = list(preferred)
        for sym in body_symbols:
            if sym not in symbols:
                symbols.append(sym)
        if not symbols:
            continue

        repo = doc.get("repo", "")
        contract_id = doc["id"]
        anchor_ids: list[str] = []
        seen_anchors: set[str] = set()

        for sym in symbols:
            # Prefer same-repo anchors. Fall back across repos so monorepo / workspace-level
            # docs (repo name = workspace) can still link symbols that live in child repos.
            resolved = resolve_anchor_ids(repo, sym, by_repo_symbol)
            if not resolved:
                resolved = resolve_anchor_ids_any_repo(sym, by_repo_symbol)
            if resolved:
                for aid in resolved:
                    if aid not in seen_anchors:
                        seen_anchors.add(aid)
                        anchor_ids.append(aid)
            else:
                stats.contract_symbols_unresolved_total += 1
                unresolved_unique.add(f"{repo}:{sym}")

        if anchor_ids:
            doc["code_anchors"] = rank_code_anchor_ids(
                anchor_ids, by_id, preferred_symbols=preferred
            )
            stats.contracts_with_code_anchors += 1
            for aid in doc["code_anchors"]:
                anchor = by_id.get(aid)
                if not anchor:
                    continue
                related = anchor.setdefault("related_doc_ids", [])
                if contract_id not in related:
                    related.append(contract_id)

    stats.unresolved_symbols = sorted(unresolved_unique)
    stats.contract_symbols_unresolved_unique = len(unresolved_unique)
    stats.anchors_with_related_doc_ids = sum(
        1 for d in manifest_docs if d.get("kind") == "code_anchor" and d.get("related_doc_ids")
    )
    return stats


def build_related_anchors_for_hit(
    doc: dict,
    by_id: dict[str, dict],
    *,
    limit: int = RELATED_ANCHORS_SEARCH_LIMIT,
) -> tuple[int, list[dict]]:
    """Ranked related anchors for search/fetch hits; full count from manifest."""
    anchor_ids = doc.get("code_anchors") or []
    total = len(anchor_ids)
    preferred = preferred_symbols_from_doc(doc)
    ranked_ids = rank_code_anchor_ids(anchor_ids, by_id, preferred_symbols=preferred)
    items: list[dict] = []
    for aid in ranked_ids[:limit]:
        anchor = by_id.get(aid)
        if not anchor:
            continue
        item: dict = {
            "doc_id": aid,
            "path": anchor.get("path", ""),
            "symbol": anchor.get("symbol"),
            "anchor_type": anchor.get("anchor_type"),
            "top_chunk_ids": [f"{aid}#0"],
        }
        if anchor.get("line_start") is not None:
            item["line_start"] = anchor["line_start"]
        if anchor.get("line_end") is not None:
            item["line_end"] = anchor["line_end"]
        items.append(item)
    return total, items
