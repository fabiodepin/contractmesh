#!/usr/bin/env python3
"""Documentation impact analysis — evidence-based docs review targets.

Pure engine module: no CLI/MCP imports. Surfaces (preflight, pr_impact, CLI, MCP)
consume the same payload.

States:
  none      — omit from cards / CLI output
  possible  — review recommended; never blocks by itself
  confirmed — demonstrable inconsistency (structural or semantic); may soft-block

Confidence qualifies inference quality, not severity.
Enforcement is separate (advisory vs soft_block).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# --- Evidence kinds (stable API for CLI/MCP/card renderers) -------------------

EVIDENCE_LINKED_SYMBOL_CHANGED = "linked_symbol_changed"
EVIDENCE_LINKED_ROUTE_CHANGED = "linked_route_changed"
EVIDENCE_DECLARED_PATH_CHANGED = "declared_path_changed"
EVIDENCE_RELATED_TEST_CHANGED = "related_test_changed"
EVIDENCE_ANCHOR_UNRESOLVED = "anchor_unresolved"
EVIDENCE_KNOWN_GAP_AFFECTED = "known_gap_affected"
EVIDENCE_SEMANTIC_MISMATCH = "semantic_mismatch"

EVIDENCE_KINDS = frozenset(
    {
        EVIDENCE_LINKED_SYMBOL_CHANGED,
        EVIDENCE_LINKED_ROUTE_CHANGED,
        EVIDENCE_DECLARED_PATH_CHANGED,
        EVIDENCE_RELATED_TEST_CHANGED,
        EVIDENCE_ANCHOR_UNRESOLVED,
        EVIDENCE_KNOWN_GAP_AFFECTED,
        EVIDENCE_SEMANTIC_MISMATCH,
    }
)

# Only these may elevate aggregate state to confirmed.
# linked_symbol_changed alone is never enough.
CONFIRMED_EVIDENCE_KINDS = frozenset(
    {
        EVIDENCE_SEMANTIC_MISMATCH,
        EVIDENCE_ANCHOR_UNRESOLVED,  # confirmed_structural
    }
)

CONFIRMATION_STRUCTURAL = "structural"
CONFIRMATION_SEMANTIC = "semantic"
STRUCTURAL_EVIDENCE_KINDS = frozenset({EVIDENCE_ANCHOR_UNRESOLVED})
SEMANTIC_EVIDENCE_KINDS = frozenset({EVIDENCE_SEMANTIC_MISMATCH})

STATE_NONE = "none"
STATE_POSSIBLE = "possible"
STATE_CONFIRMED = "confirmed"

# Public fields every surface must preserve without remapping.
CORE_PAYLOAD_KEYS = (
    "state",
    "confidence",
    "enforcement",
    "confirmation_kind",
    "documents",
    "summary",
)

DEPRECATION_DOCS_DRIFT_CHECK = {
    "deprecated": True,
    "replacement": "documentation_impact",
    "replacement_cli": "contractmesh docs impact",
    "message": (
        "docs_drift_check is deprecated; use documentation_impact "
        "/ contractmesh docs impact"
    ),
}

CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"

ENFORCEMENT_NONE = "none"
ENFORCEMENT_ADVISORY = "advisory"
ENFORCEMENT_SOFT_BLOCK = "soft_block"

DOC_KINDS = frozenset({"contract", "adr", "integrations", "architecture", "known_gaps"})
CODE_EXTENSIONS = {
    ".java",
    ".kt",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".py",
    ".yml",
    ".yaml",
}
TEST_PATH_HINTS = (
    "/test/",
    "/tests/",
    "tests/",
    "test/",
    "_test.",
    ".test.",
    "Test.java",
    "spec.ts",
    "spec.tsx",
)


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _paths_match(changed: str, indexed: str) -> bool:
    changed = _normalize_path(changed)
    indexed = _normalize_path(indexed)
    if not changed or not indexed:
        return False
    return changed == indexed or changed.endswith("/" + indexed) or indexed.endswith("/" + changed)


def _is_code_path(path: str) -> bool:
    return Path(path).suffix.lower() in CODE_EXTENSIONS


def _is_doc_path(path: str) -> bool:
    lower = _normalize_path(path).lower()
    return lower.endswith(".md") and ("/docs/" in lower or lower.startswith("docs/"))


def _is_test_path(path: str) -> bool:
    lower = _normalize_path(path).lower()
    if not _is_code_path(lower):
        return False
    return any(hint.lower() in lower for hint in TEST_PATH_HINTS)


def empty_documentation_impact() -> dict[str, Any]:
    return {
        "state": STATE_NONE,
        "confidence": CONFIDENCE_LOW,
        "enforcement": ENFORCEMENT_NONE,
        "confirmation_kind": None,
        "documents": [],
        "summary": None,
    }


def evidence_source(
    *,
    repo: str | None = None,
    path: str | None = None,
    symbol: str | None = None,
    line: int | None = None,
) -> dict[str, Any] | None:
    """Optional provenance for a reason (repo/path/symbol/line)."""
    source: dict[str, Any] = {}
    if repo:
        source["repo"] = str(repo)
    if path:
        source["path"] = _normalize_path(str(path))
    if symbol:
        source["symbol"] = str(symbol)
    if line is not None:
        try:
            source["line"] = int(line)
        except (TypeError, ValueError):
            pass
    return source or None


def core_documentation_impact(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip surface-only fields so engine/CLI/MCP/preflight/pr_impact can be compared."""
    core = {k: payload.get(k) for k in CORE_PAYLOAD_KEYS}
    # Normalize documents to comparable shape (kinds + ids + reason kinds/sources).
    docs = []
    for doc in payload.get("documents") or []:
        reasons = []
        for reason in doc.get("reasons") or []:
            item = {"kind": reason.get("kind")}
            if reason.get("symbols") is not None:
                item["symbols"] = list(reason.get("symbols") or [])
            if reason.get("paths") is not None:
                item["paths"] = list(reason.get("paths") or [])
            if reason.get("source") is not None:
                item["source"] = dict(reason.get("source") or {})
            if reason.get("classification") is not None:
                item["classification"] = reason.get("classification")
            if reason.get("detail") is not None:
                item["detail"] = reason.get("detail")
            reasons.append(item)
        docs.append(
            {
                "id": doc.get("id"),
                "path": doc.get("path"),
                "kind": doc.get("kind"),
                "reasons": reasons,
                "review_topics": list(doc.get("review_topics") or []),
            }
        )
    core["documents"] = docs
    return core


def _index_by_id(manifest: dict) -> dict[str, dict]:
    return {d.get("id", ""): d for d in manifest.get("documents", []) if d.get("id")}


def _ensure_doc(
    buckets: dict[str, dict[str, Any]],
    doc: dict,
) -> dict[str, Any]:
    doc_id = str(doc.get("external_id") or doc.get("id") or doc.get("path") or "")
    path = _normalize_path(str(doc.get("path") or ""))
    key = doc_id or path
    if key not in buckets:
        buckets[key] = {
            "id": doc_id,
            "path": path,
            "kind": str(doc.get("kind") or ""),
            "title": str(doc.get("title") or ""),
            "reasons": [],
            "review_topics": [],
        }
    return buckets[key]


def _add_reason(
    entry: dict[str, Any],
    *,
    kind: str,
    symbols: list[str] | None = None,
    paths: list[str] | None = None,
    detail: str | None = None,
    structural: bool = False,
    source: dict[str, Any] | None = None,
) -> None:
    if kind not in EVIDENCE_KINDS:
        raise ValueError(f"unknown evidence kind: {kind}")
    reason: dict[str, Any] = {"kind": kind}
    if symbols:
        reason["symbols"] = sorted(set(symbols))
    if paths:
        reason["paths"] = sorted({_normalize_path(p) for p in paths if p})
    if detail:
        reason["detail"] = detail
    if structural:
        reason["classification"] = "confirmed_structural"
    if source:
        reason["source"] = source
    # Dedupe by kind + symbols + paths + source path/symbol
    src = reason.get("source") or {}
    sig = (
        kind,
        tuple(reason.get("symbols") or []),
        tuple(reason.get("paths") or []),
        reason.get("detail") or "",
        src.get("path") or "",
        src.get("symbol") or "",
    )
    existing = {
        (
            r.get("kind"),
            tuple(r.get("symbols") or []),
            tuple(r.get("paths") or []),
            r.get("detail") or "",
            (r.get("source") or {}).get("path") or "",
            (r.get("source") or {}).get("symbol") or "",
        )
        for r in entry["reasons"]
    }
    if sig not in existing:
        entry["reasons"].append(reason)


def _default_review_topics(kind: str, title: str) -> list[str]:
    topics: list[str] = []
    blob = f"{kind} {title}".lower()
    if any(tok in blob for tok in ("auth", "login", "token", "jwt", "session")):
        topics.extend(["error codes", "token claims"])
    if any(tok in blob for tok in ("mailbox", "email account", "provision")):
        topics.extend(["provisioning rules", "quota enforcement"])
    if any(tok in blob for tok in ("tenant", "isolation", "multitenan")):
        topics.extend(["tenant isolation", "schema routing"])
    if not topics:
        topics.append("behavior and ownership boundaries")
    # stable unique
    return list(dict.fromkeys(topics))


def _infer_confidence(documents: list[dict[str, Any]], state: str) -> str:
    if state == STATE_NONE:
        return CONFIDENCE_LOW
    reason_kinds: set[str] = set()
    reason_count = 0
    for doc in documents:
        for reason in doc.get("reasons") or []:
            reason_kinds.add(str(reason.get("kind")))
            reason_count += 1
    strong = reason_kinds & CONFIRMED_EVIDENCE_KINDS
    if strong or (reason_count >= 3 and len(documents) >= 2):
        return CONFIDENCE_HIGH
    if reason_count >= 2 or (EVIDENCE_RELATED_TEST_CHANGED in reason_kinds):
        return CONFIDENCE_MEDIUM
    if EVIDENCE_KNOWN_GAP_AFFECTED in reason_kinds and reason_count >= 1:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def _infer_enforcement(state: str) -> str:
    if state == STATE_CONFIRMED:
        return ENFORCEMENT_SOFT_BLOCK
    if state == STATE_POSSIBLE:
        return ENFORCEMENT_ADVISORY
    return ENFORCEMENT_NONE


def _infer_confirmation_kind(documents: list[dict[str, Any]], state: str) -> str | None:
    """Public confirmation_kind while state stays confirmed.

    Prefer semantic when both are present — it usually drives stronger policy copy.
    """
    if state != STATE_CONFIRMED:
        return None
    kinds = {
        str(reason.get("kind"))
        for doc in documents
        for reason in (doc.get("reasons") or [])
    }
    if kinds & SEMANTIC_EVIDENCE_KINDS:
        return CONFIRMATION_SEMANTIC
    if kinds & STRUCTURAL_EVIDENCE_KINDS:
        return CONFIRMATION_STRUCTURAL
    return None


def _aggregate_state(documents: list[dict[str, Any]]) -> str:
    if not documents:
        return STATE_NONE
    for doc in documents:
        for reason in doc.get("reasons") or []:
            if reason.get("kind") in CONFIRMED_EVIDENCE_KINDS:
                return STATE_CONFIRMED
    return STATE_POSSIBLE


def _summary_for(state: str, documents: list[dict[str, Any]]) -> str | None:
    if state == STATE_NONE:
        return None
    labels = [d.get("id") or d.get("path") for d in documents[:3] if d.get("id") or d.get("path")]
    joined = ", ".join(str(x) for x in labels if x)
    if state == STATE_CONFIRMED:
        return f"Confirmed documentation inconsistency involving {joined}."
    return f"Docs review recommended for {joined}."


def compute_documentation_impact(
    *,
    changed_paths: list[str] | None = None,
    manifest: dict,
    confirmed_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build documentation_impact payload from path diff and/or confirmed findings.

    Rules:
    - "code changed and linked doc did not" → possible only (linked_symbol_changed).
    - confirmed requires CONFIRMED_EVIDENCE_KINDS (never linked_symbol alone).
    """
    changed_paths = [_normalize_path(p) for p in (changed_paths or []) if p]
    changed_set = set(changed_paths)
    by_id = _index_by_id(manifest)
    buckets: dict[str, dict[str, Any]] = {}

    code_changes = [
        p
        for p in changed_paths
        if _is_code_path(p) and not p.startswith(".contractmesh/") and not _is_test_path(p)
    ]
    test_changes = [p for p in changed_paths if _is_test_path(p)]

    code_anchor_docs = [
        d
        for d in manifest.get("documents", [])
        if d.get("kind") == "code_anchor"
        and any(_paths_match(changed, d.get("path", "")) for changed in code_changes)
    ]
    test_anchor_docs = [
        d
        for d in manifest.get("documents", [])
        if d.get("kind") == "test_anchor"
        and any(_paths_match(changed, d.get("path", "")) for changed in test_changes)
    ]

    # 1) linked_symbol_changed — possible only
    for anchor in code_anchor_docs:
        symbol = str(anchor.get("symbol") or "")
        code_path = _normalize_path(str(anchor.get("path") or ""))
        for doc_id in anchor.get("related_doc_ids") or []:
            related = by_id.get(doc_id)
            if not related or related.get("kind") not in DOC_KINDS:
                continue
            doc_path = _normalize_path(str(related.get("path") or ""))
            if doc_path in changed_set:
                continue
            entry = _ensure_doc(buckets, related)
            _add_reason(
                entry,
                kind=EVIDENCE_LINKED_SYMBOL_CHANGED,
                symbols=[symbol] if symbol else None,
                paths=[code_path] if code_path else None,
                source=evidence_source(
                    repo=anchor.get("repo"),
                    path=code_path or None,
                    symbol=symbol or None,
                    line=anchor.get("line_start"),
                ),
            )

    # Contracts that list code_anchors whose paths changed
    for doc in manifest.get("documents", []):
        if doc.get("kind") != "contract":
            continue
        contract_path = _normalize_path(str(doc.get("path") or ""))
        if contract_path in changed_set:
            continue
        changed_symbols: list[str] = []
        changed_anchor_paths: list[str] = []
        primary_source: dict[str, Any] | None = None
        for aid in doc.get("code_anchors") or []:
            anchor = by_id.get(aid)
            if not anchor:
                continue
            anchor_path = _normalize_path(str(anchor.get("path") or ""))
            if any(_paths_match(changed, anchor_path) for changed in code_changes):
                if anchor.get("symbol"):
                    changed_symbols.append(str(anchor["symbol"]))
                if anchor_path:
                    changed_anchor_paths.append(anchor_path)
                if primary_source is None:
                    primary_source = evidence_source(
                        repo=anchor.get("repo"),
                        path=anchor_path or None,
                        symbol=anchor.get("symbol"),
                        line=anchor.get("line_start"),
                    )
        if not changed_symbols and not changed_anchor_paths:
            continue
        entry = _ensure_doc(buckets, doc)
        _add_reason(
            entry,
            kind=EVIDENCE_LINKED_SYMBOL_CHANGED,
            symbols=changed_symbols or None,
            paths=changed_anchor_paths or None,
            source=primary_source,
        )

    # 2) related_test_changed — tests linked to the same docs
    for test_doc in test_anchor_docs:
        test_path = _normalize_path(str(test_doc.get("path") or ""))
        related_ids = list(test_doc.get("related_doc_ids") or [])
        # Also attribute tests to contracts that share symbols with the test name/path
        test_sym = str(test_doc.get("symbol") or "").lower()
        for doc in manifest.get("documents", []):
            if doc.get("kind") not in DOC_KINDS:
                continue
            doc_id = doc.get("id", "")
            hit = doc_id in related_ids
            if not hit:
                for aid in doc.get("code_anchors") or []:
                    anchor = by_id.get(aid)
                    if not anchor:
                        continue
                    asym = str(anchor.get("symbol") or "").lower()
                    if asym and len(asym) >= 5 and asym in test_sym:
                        hit = True
                        break
            if not hit:
                continue
            doc_path = _normalize_path(str(doc.get("path") or ""))
            if doc_path in changed_set:
                continue
            entry = _ensure_doc(buckets, doc)
            _add_reason(
                entry,
                kind=EVIDENCE_RELATED_TEST_CHANGED,
                paths=[test_path] if test_path else None,
                source=evidence_source(
                    repo=test_doc.get("repo"),
                    path=test_path or None,
                    symbol=test_doc.get("symbol"),
                    line=test_doc.get("line_start"),
                ),
            )

    # 3) known_gap_affected — for docs already in buckets or contracts touched by code
    touched_keys = set(buckets.keys())
    for key, entry in list(buckets.items()):
        # Resolve full doc for gap ids
        for doc in manifest.get("documents", []):
            ext = str(doc.get("external_id") or doc.get("id") or "")
            path = _normalize_path(str(doc.get("path") or ""))
            if ext != entry["id"] and path != entry["path"]:
                continue
            gaps = [str(g) for g in (doc.get("known_gap_ids") or []) if g]
            if gaps:
                _add_reason(
                    entry,
                    kind=EVIDENCE_KNOWN_GAP_AFFECTED,
                    detail=", ".join(gaps[:5]),
                )
            break

    # 4) confirmed findings (structural / semantic) — scoped when possible
    for finding in confirmed_findings or []:
        drift_type = str(finding.get("drift_type") or finding.get("kind") or "")
        summary = str(finding.get("summary") or "")
        if drift_type == "anchor_unresolved" or drift_type == EVIDENCE_ANCHOR_UNRESOLVED:
            evidence_kind = EVIDENCE_ANCHOR_UNRESOLVED
            structural = True
        elif drift_type in ("semantic_mismatch", EVIDENCE_SEMANTIC_MISMATCH) or finding.get(
            "kind"
        ) == EVIDENCE_SEMANTIC_MISMATCH:
            evidence_kind = EVIDENCE_SEMANTIC_MISMATCH
            structural = False
        else:
            # Unknown demonstrable types stay out of documentation_impact until mapped.
            continue

        target_docs: list[dict] = []
        path_hint = _normalize_path(str(finding.get("path") or finding.get("doc_path") or ""))
        external = str(finding.get("external_id") or finding.get("contract_id") or "")
        for doc in manifest.get("documents", []):
            if doc.get("kind") not in DOC_KINDS:
                continue
            doc_path = _normalize_path(str(doc.get("path") or ""))
            doc_ext = str(doc.get("external_id") or "")
            if external and doc_ext == external:
                target_docs.append(doc)
            elif path_hint and _paths_match(path_hint, doc_path):
                target_docs.append(doc)
            elif evidence_kind == EVIDENCE_ANCHOR_UNRESOLVED and summary:
                # Attach unresolved symbol findings to contracts that declare the symbol.
                for raw in doc.get("related_anchors") or []:
                    sym = str(raw).split(".", 1)[0]
                    if sym and sym in summary:
                        target_docs.append(doc)
                        break

        if not target_docs and evidence_kind == EVIDENCE_ANCHOR_UNRESOLVED:
            # Global structural finding: attach to contracts that have unresolved risk
            # only when we already have possible impact on them, else skip noise.
            for key in touched_keys:
                entry = buckets[key]
                for doc in manifest.get("documents", []):
                    if (doc.get("external_id") or doc.get("id")) == entry["id"] or _normalize_path(
                        str(doc.get("path") or "")
                    ) == entry["path"]:
                        target_docs.append(doc)
                        break

        if not target_docs and evidence_kind == EVIDENCE_SEMANTIC_MISMATCH:
            # Require an explicit path/external_id for semantic findings.
            continue

        for doc in target_docs:
            entry = _ensure_doc(buckets, doc)
            _add_reason(
                entry,
                kind=evidence_kind,
                detail=summary or None,
                structural=structural,
                source=evidence_source(
                    repo=finding.get("repo"),
                    path=finding.get("path") or finding.get("code_path"),
                    symbol=finding.get("symbol"),
                    line=finding.get("line"),
                ),
            )

    documents = []
    for entry in buckets.values():
        if not entry["reasons"]:
            continue
        if not entry["review_topics"]:
            entry["review_topics"] = _default_review_topics(entry["kind"], entry["title"])
        documents.append(entry)

    documents.sort(key=lambda d: (d.get("path") or "", d.get("id") or ""))
    state = _aggregate_state(documents)
    confidence = _infer_confidence(documents, state)
    enforcement = _infer_enforcement(state)
    confirmation_kind = _infer_confirmation_kind(documents, state)

    return {
        "state": state,
        "confidence": confidence,
        "enforcement": enforcement,
        "confirmation_kind": confirmation_kind,
        "documents": documents,
        "summary": _summary_for(state, documents),
    }


def format_documentation_impact(result: dict[str, Any]) -> str | None:
    """Human-readable card. Returns None when state is none (silence)."""
    if not result or result.get("state") == STATE_NONE:
        return None
    lines = ["Docs review recommended", ""]
    for doc in result.get("documents") or []:
        label = doc.get("id") or doc.get("path") or "document"
        lines.append(str(label))
        reasons = doc.get("reasons") or []
        reason_bits: list[str] = []
        for reason in reasons:
            kind = reason.get("kind")
            if kind == EVIDENCE_LINKED_SYMBOL_CHANGED:
                syms = reason.get("symbols") or []
                reason_bits.append(
                    f"{len(syms)} linked symbol(s) changed"
                    if syms
                    else "linked symbols changed"
                )
            elif kind == EVIDENCE_RELATED_TEST_CHANGED:
                reason_bits.append("related tests were modified")
            elif kind == EVIDENCE_KNOWN_GAP_AFFECTED:
                reason_bits.append(f"known gap(s): {reason.get('detail') or 'affected'}")
            elif kind == EVIDENCE_ANCHOR_UNRESOLVED:
                reason_bits.append("unresolved contract anchors")
            elif kind == EVIDENCE_SEMANTIC_MISMATCH:
                reason_bits.append(reason.get("detail") or "semantic mismatch")
            else:
                reason_bits.append(str(kind))
        if reason_bits:
            lines.append(f"Reason: {'; '.join(reason_bits)}.")
        topics = doc.get("review_topics") or []
        if topics:
            lines.append(f"Review: {', '.join(topics)}.")
        lines.append("")
    lines.append(
        f"state={result.get('state')} confidence={result.get('confidence')} "
        f"enforcement={result.get('enforcement')}"
        + (
            f" confirmation_kind={result.get('confirmation_kind')}"
            if result.get("confirmation_kind")
            else ""
        )
    )
    return "\n".join(lines).rstrip() + "\n"


def documentation_impact_card_lines(result: dict[str, Any]) -> list[str]:
    """Compact lines for preflight cards; empty when state is none."""
    if not result or result.get("state") == STATE_NONE:
        return []
    labels = []
    for doc in result.get("documents") or []:
        labels.append(str(doc.get("id") or doc.get("path") or ""))
    labels = [x for x in labels if x][:4]
    text = format_documentation_impact(result)
    if not text:
        return []
    return [
        f"Docs: {result.get('state')} ({result.get('enforcement')}) — {', '.join(labels)}",
    ]
