#!/usr/bin/env python3
"""Preflight check before editing a symbol — contracts, gaps, tests, drift, risk."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .documentation_impact import (
    STATE_CONFIRMED,
    STATE_NONE,
    compute_documentation_impact,
    documentation_impact_card_lines,
    format_documentation_impact,
)
from .workspace_manifest import load_workspace_manifest
from .workspace_search import (
    _dedupe_doc_refs,
    _source_refs,
    impact_analysis,
    list_drift,
    related_tests,
)

METHOD_SUFFIX_RE = re.compile(r"^([A-Z][A-Za-z0-9]+)\.([a-z][A-Za-z0-9_]*)$")
CAMEL_SPLIT_RE = re.compile(r"(?=[A-Z])")

DOMAIN_PHRASES: dict[str, str] = {
    "tenant": "tenant isolation",
    "isolation": "tenant isolation",
    "mailbox": "mailbox provisioning",
    "mail": "mailbox provisioning",
    "auth": "authentication",
    "authentication": "authentication",
    "security": "security controls",
    "billing": "billing",
    "provisioning": "mailbox provisioning",
}

TITLE_PHRASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"tenant", re.I), "tenant isolation"),
    (re.compile(r"mailbox|email.?account", re.I), "mailbox provisioning"),
    (re.compile(r"auth|login|session", re.I), "authentication"),
    (re.compile(r"security|rbac|permission", re.I), "security controls"),
    (re.compile(r"provision", re.I), "provisioning"),
)


def _symbol_search_query(class_symbol: str, contracts: list[dict[str, Any]]) -> str:
    parts = [p.lower() for p in CAMEL_SPLIT_RE.split(class_symbol) if p]
    extra: list[str] = []
    for contract in contracts:
        title = str(contract.get("title") or contract.get("external_id") or "")
        extra.extend(re.split(r"[\s\-_/]+", title.lower()))
    tokens = parts + [t for t in extra if len(t) > 2]
    return " ".join(dict.fromkeys(tokens))


def parse_symbol_target(symbol: str) -> tuple[str, str | None]:
    """Split EmailAccountService.create → (EmailAccountService, create)."""
    symbol = symbol.strip()
    match = METHOD_SUFFIX_RE.match(symbol)
    if match:
        return match.group(1), match.group(2)
    return symbol, None


def _preflight_config(workspace: Path) -> dict[str, Any]:
    return load_workspace_manifest(workspace).get("preflight") or {}


def _contract_labels(contracts: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for item in contracts:
        label = str(item.get("external_id") or item.get("title") or item.get("path") or "")
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels


def _gap_ids(gap_docs: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for item in gap_docs:
        for gap_id in item.get("known_gap_ids") or []:
            if gap_id not in seen:
                seen.add(gap_id)
                ids.append(gap_id)
    return sorted(ids)


def _test_label(item: dict[str, Any]) -> str:
    symbol = item.get("symbol")
    if symbol:
        return str(symbol)
    return Path(str(item.get("path", ""))).stem


def _test_priority(label: str) -> int:
    lowered = label.lower()
    if lowered.endswith("contracttest"):
        return 0
    if lowered.endswith("integrationtest"):
        return 1
    if lowered.endswith("securitytest"):
        return 2
    if lowered.endswith("test"):
        return 3
    return 4


def _test_labels(tests: list[dict[str, Any]], *, limit: int = 4) -> list[str]:
    ranked = sorted(
        {_test_label(item) for item in tests if _test_label(item)},
        key=lambda label: (_test_priority(label), label),
    )
    return ranked[:limit]


def _why_summary(
    *,
    contracts: list[dict[str, Any]],
    adrs: list[dict[str, Any]],
    gap_ids: list[str],
    class_symbol: str,
) -> str:
    phrases: list[str] = []
    seen: set[str] = set()

    def add_phrase(phrase: str) -> None:
        phrase = phrase.strip()
        if not phrase or phrase in seen:
            return
        seen.add(phrase)
        phrases.append(phrase)

    for contract in contracts:
        owner = contract.get("owner") or {}
        if isinstance(owner, dict):
            for key in ("domain", "team"):
                domain = str(owner.get(key) or "").lower()
                if domain in DOMAIN_PHRASES:
                    add_phrase(DOMAIN_PHRASES[domain])
        for field in ("title", "external_id"):
            text = str(contract.get(field) or "")
            for pattern, phrase in TITLE_PHRASES:
                if pattern.search(text):
                    add_phrase(phrase)

    for adr in adrs:
        title = str(adr.get("title") or "")
        for pattern, phrase in TITLE_PHRASES:
            if pattern.search(title):
                add_phrase(phrase)

    if gap_ids:
        add_phrase("known enforcement gaps")

    if not phrases:
        parts = [p.lower() for p in CAMEL_SPLIT_RE.split(class_symbol) if p]
        if parts:
            add_phrase(f"{parts[0]} behavior")
        else:
            add_phrase("indexed cross-cutting behavior")

    if len(phrases) == 1:
        return f"touches {phrases[0]}"
    return "touches " + " + ".join(phrases[:3])


def _review_labels(contracts: list[dict[str, Any]], gap_ids: list[str], *, limit: int = 4) -> list[str]:
    labels = _contract_labels(contracts)
    for gap_id in gap_ids:
        if gap_id not in labels:
            labels.append(gap_id)
    return labels[:limit]


def _drift_for_symbol(manifest: dict, class_symbol: str) -> list[dict[str, Any]]:
    findings = list_drift(manifest).get("findings") or []
    matched: list[dict[str, Any]] = []
    needle = class_symbol.lower()
    for item in findings:
        summary = str(item.get("summary", "")).lower()
        if needle in summary or class_symbol in str(item.get("contract_id", "")):
            matched.append(item)
    unresolved = manifest.get("build_stats") or {}
    unique = unresolved.get("contract_symbols_unresolved_unique") or []
    if isinstance(unique, list) and class_symbol in unique:
        matched.append(
            {
                "drift_type": "anchor_unresolved",
                "summary": f"Contract references '{class_symbol}' but no code anchor was indexed",
                "trust_level": "detected_mismatch",
            }
        )
    return matched


def _assess_risk(
    *,
    contracts: list[dict[str, Any]],
    gap_ids: list[str],
    tests: list[dict[str, Any]],
    drift: list[dict[str, Any]],
    adrs: list[dict[str, Any]],
    method: str | None,
    config: dict[str, Any],
) -> str:
    score = 0
    if contracts:
        score += int(config.get("contract_weight", 2))
    if len(contracts) >= 2:
        score += int(config.get("multi_contract_weight", 1))
    if gap_ids:
        score += int(config.get("gap_weight", 3))
    if not tests:
        score += int(config.get("no_tests_weight", 2))
    elif len(tests) < 2:
        score += int(config.get("low_tests_weight", 1))
    if drift:
        score += int(config.get("drift_weight", 2))
    if adrs:
        score += int(config.get("adr_weight", 1))
    if method:
        score += int(config.get("method_weight", 1))

    high_min = int(config.get("high_min_score", 6))
    medium_min = int(config.get("medium_min_score", 3))
    if score >= high_min:
        return "HIGH"
    if score >= medium_min:
        return "MEDIUM"
    return "LOW"


def _recommendation(
    *,
    class_symbol: str,
    method: str | None,
    contracts: list[dict[str, Any]],
    gap_ids: list[str],
    tests: list[dict[str, Any]],
    drift: list[dict[str, Any]],
    risk: str,
) -> str:
    parts: list[str] = []
    if contracts:
        primary = _contract_labels(contracts)[0]
        parts.append(f"Review {primary} before editing {class_symbol}.")
    else:
        parts.append(f"No indexed contract found for {class_symbol}; confirm ownership before editing.")

    if method:
        parts.append(f"Method `{method}` may affect behavior covered by linked contracts and tests.")

    if gap_ids:
        parts.append(f"Known gaps apply ({', '.join(gap_ids[:3])}); changes may not be fully enforced yet.")

    if not tests:
        parts.append("No indexed tests matched — add or run integration tests before merging.")

    if drift:
        parts.append("Drift detected between docs and implementation; reconcile contracts first.")

    if risk == "HIGH":
        parts.append("Treat this as a high-impact change: read contracts, gaps and tests before patching.")
    elif risk == "LOW" and not gap_ids and not drift:
        parts.append("Lower indexed risk, but still verify behavior against contracts.")

    return " ".join(parts)


def _agent_policy(
    *,
    risk: str,
    symbol: str,
    review: list[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    enabled = bool(config.get("soft_block_enabled", True))
    require_for = [str(v).upper() for v in (config.get("soft_block_require") or ["HIGH"])]
    requires_confirmation = enabled and risk in require_for
    policy: dict[str, Any] = {
        "requires_confirmation": requires_confirmation,
        "do_not_patch_until_confirmed": requires_confirmation,
    }
    if requires_confirmation:
        review_hint = ", ".join(review[:3]) if review else "linked contracts and tests"
        policy["confirmation_prompt"] = (
            f"Risk is {risk} for {symbol}. Confirm you reviewed {review_hint} before editing."
        )
    return policy


def _build_card(
    *,
    risk: str,
    why: str,
    review: list[str],
    run: list[str],
    drift_summary: str | list[str],
    docs_lines: list[str] | None = None,
) -> dict[str, Any]:
    drift_line = drift_summary if isinstance(drift_summary, str) else "; ".join(drift_summary[:2]) or "none"
    card = {
        "risk": risk,
        "why": why,
        "review": review,
        "run": run,
        "drift": drift_line,
    }
    lines = [
        f"Risk: {risk}",
        f"Why: {why}",
        f"Review: {', '.join(review) if review else 'none'}",
        f"Run: {', '.join(run) if run else 'none'}",
    ]
    if drift_line != "none":
        lines.append(f"Drift: {drift_line}")
    for docs_line in docs_lines or []:
        lines.append(docs_line)
    card["text"] = "\n".join(lines)
    return card


def _documentation_impact_for_preflight(
    manifest: dict,
    *,
    class_symbol: str,
    contracts: list[dict[str, Any]],
    drift_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Preflight has no git diff: only confirmed findings + gaps on linked contracts."""
    confirmed: list[dict[str, Any]] = []
    for item in drift_items:
        drift_type = str(item.get("drift_type") or "")
        if drift_type == "anchor_unresolved":
            confirmed.append(
                {
                    "drift_type": "anchor_unresolved",
                    "summary": item.get("summary") or f"Unresolved anchor related to {class_symbol}",
                }
            )
        elif drift_type == "semantic_mismatch":
            confirmed.append(
                {
                    "drift_type": "semantic_mismatch",
                    "summary": item.get("summary"),
                    "external_id": item.get("external_id"),
                    "path": item.get("path"),
                }
            )

    # Seed possible impact via synthetic empty code change is wrong.
    # Instead, attach known_gap_affected by temporarily marking linked contract
    # paths as unchanged and injecting gap reasons through confirmed/gaps path:
    impact = compute_documentation_impact(
        changed_paths=[],
        manifest=manifest,
        confirmed_findings=confirmed,
    )
    if impact.get("state") != STATE_NONE:
        return impact

    # Advisory: known gaps on linked contracts (no code-diff signal).
    buckets: list[dict[str, Any]] = []
    for contract in contracts:
        gaps = []
        # contracts from impact may already expose known_gap_ids
        gaps = list(contract.get("known_gap_ids") or [])
        if not gaps:
            for doc in manifest.get("documents", []):
                if doc.get("external_id") and doc.get("external_id") == contract.get("external_id"):
                    gaps = list(doc.get("known_gap_ids") or [])
                    break
        if not gaps:
            continue
        buckets.append(
            {
                "id": contract.get("external_id") or contract.get("doc_id") or "",
                "path": contract.get("path") or "",
                "kind": "contract",
                "title": contract.get("title") or "",
                "reasons": [
                    {
                        "kind": "known_gap_affected",
                        "detail": ", ".join(str(g) for g in gaps[:5]),
                    }
                ],
                "review_topics": ["known gaps", "enforcement boundaries"],
            }
        )
    if not buckets:
        return impact
    return {
        "state": "possible",
        "confidence": "medium",
        "enforcement": "advisory",
        "confirmation_kind": None,
        "documents": buckets,
        "summary": f"Docs review recommended for {', '.join(str(b.get('id') or b.get('path')) for b in buckets[:3])}.",
    }


def _contracts_for_class_symbol(manifest: dict, class_symbol: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve contracts and code anchors linked to a class symbol."""
    by_id = {d.get("id"): d for d in manifest.get("documents", []) if d.get("id")}
    contracts: list[dict[str, Any]] = []
    anchors: list[dict[str, Any]] = []
    seen_contract: set[str] = set()
    seen_anchor: set[str] = set()

    def absorb_contract(doc: dict | None) -> None:
        if not doc or doc.get("kind") != "contract":
            return
        doc_id = doc.get("id", "")
        if doc_id in seen_contract:
            return
        seen_contract.add(doc_id)
        contracts.append(
            {
                "doc_id": doc_id,
                "external_id": doc.get("external_id"),
                "path": doc.get("path", ""),
                "title": doc.get("title", ""),
                "kind": "contract",
                "owner": doc.get("owner") or {},
            }
        )

    def absorb_anchor(doc: dict | None) -> None:
        if not doc or doc.get("kind") != "code_anchor":
            return
        doc_id = doc.get("id", "")
        if doc_id in seen_anchor:
            return
        seen_anchor.add(doc_id)
        anchors.append(
            {
                "doc_id": doc_id,
                "symbol": doc.get("symbol"),
                "path": doc.get("path", ""),
                "kind": "code_anchor",
                "repo": doc.get("repo", ""),
            }
        )

    for doc in manifest.get("documents", []):
        if doc.get("kind") == "code_anchor" and doc.get("symbol") == class_symbol:
            absorb_anchor(doc)
            for doc_id in doc.get("related_doc_ids") or []:
                absorb_contract(by_id.get(doc_id))

    anchor_ids = {a["doc_id"] for a in anchors}
    for doc in manifest.get("documents", []):
        if doc.get("kind") != "contract":
            continue
        for aid in doc.get("code_anchors") or []:
            if aid in anchor_ids:
                absorb_contract(doc)
                break

    return contracts, anchors


def preflight_change(
    workspace: Path,
    manifest: dict,
    local_by_id: dict[str, dict],
    *,
    symbol: str,
    repo: str | list[str] | None = None,
    limit: int = 8,
) -> tuple[dict[str, Any], str | None]:
    """Preflight card: are you sure you want to edit this symbol?"""
    if not symbol or not symbol.strip():
        return {}, "symbol is required"

    class_symbol, method = parse_symbol_target(symbol.strip())
    preflight_cfg = _preflight_config(workspace)

    impact, err = impact_analysis(
        workspace,
        manifest,
        local_by_id,
        symbol=class_symbol,
        repo=repo,
        limit=limit,
    )
    if err:
        return {}, err

    symbol_contracts, symbol_anchors = _contracts_for_class_symbol(manifest, class_symbol)

    tests_result, err = related_tests(
        workspace,
        manifest,
        local_by_id,
        symbol=class_symbol,
        repo=repo,
        limit=limit,
    )
    if err:
        return {}, err

    contracts = impact.get("contracts") or []
    if not contracts and symbol_contracts:
        contracts = symbol_contracts
    adrs = impact.get("adrs") or []
    gap_docs = impact.get("known_gaps") or []
    if not gap_docs and contracts:
        for doc in manifest.get("documents", []):
            if doc.get("kind") != "contract":
                continue
            ext = doc.get("external_id")
            if ext and any(c.get("external_id") == ext for c in contracts):
                if doc.get("known_gap_ids"):
                    gap_docs.append(
                        {
                            "doc_id": doc.get("id"),
                            "path": doc.get("path", ""),
                            "kind": "contract",
                            "known_gap_ids": doc.get("known_gap_ids"),
                        }
                    )
    gap_ids = _gap_ids(gap_docs)
    test_items = tests_result.get("related_tests") or []
    if not test_items and contracts:
        fallback_query = _symbol_search_query(class_symbol, contracts)
        fallback, err = related_tests(
            workspace,
            manifest,
            local_by_id,
            query=fallback_query,
            symbol=class_symbol,
            repo=repo,
            limit=limit,
        )
        if not err:
            test_items = fallback.get("related_tests") or []
    if not test_items and contracts:
        # Last resort: query-only, still ranked but may include neighbors.
        fallback_query = _symbol_search_query(class_symbol, contracts)
        fallback, err = related_tests(
            workspace,
            manifest,
            local_by_id,
            query=fallback_query,
            repo=repo,
            limit=limit,
        )
        if not err:
            test_items = fallback.get("related_tests") or []
    code_anchors = impact.get("code_anchors") or symbol_anchors
    drift_items = _drift_for_symbol(manifest, class_symbol)
    risk = _assess_risk(
        contracts=contracts,
        gap_ids=gap_ids,
        tests=test_items,
        drift=drift_items,
        adrs=adrs,
        method=method,
        config=preflight_cfg,
    )
    why = _why_summary(contracts=contracts, adrs=adrs, gap_ids=gap_ids, class_symbol=class_symbol)
    review = _review_labels(contracts, gap_ids)
    run = _test_labels(test_items)
    if drift_items:
        seen_drift: set[str] = set()
        drift_summary: str | list[str] = []
        for item in drift_items:
            summary = str(item.get("summary", ""))
            if summary and summary not in seen_drift:
                seen_drift.add(summary)
                drift_summary.append(summary)  # type: ignore[union-attr]
    else:
        drift_summary = "none"
    recommendation = _recommendation(
        class_symbol=class_symbol,
        method=method,
        contracts=contracts,
        gap_ids=gap_ids,
        tests=test_items,
        drift=drift_items,
        risk=risk,
    )
    agent_policy = _agent_policy(
        risk=risk,
        symbol=symbol.strip(),
        review=review,
        config=preflight_cfg,
    )
    doc_impact = _documentation_impact_for_preflight(
        manifest,
        class_symbol=class_symbol,
        contracts=contracts,
        drift_items=drift_items,
    )
    if doc_impact.get("state") == STATE_CONFIRMED:
        agent_policy = dict(agent_policy)
        if bool(preflight_cfg.get("soft_block_enabled", True)):
            agent_policy["requires_confirmation"] = True
            agent_policy["do_not_patch_until_confirmed"] = True
            agent_policy["confirmation_prompt"] = (
                agent_policy.get("confirmation_prompt")
                or f"Confirmed documentation impact for {symbol.strip()}. Review linked docs before editing."
            )
            agent_policy["documentation_enforcement"] = doc_impact.get("enforcement")

    docs_lines = documentation_impact_card_lines(doc_impact)
    card = _build_card(
        risk=risk,
        why=why,
        review=review,
        run=run,
        drift_summary=drift_summary,
        docs_lines=docs_lines,
    )

    all_refs = contracts + adrs + gap_docs + test_items + [
        {"path": d.get("summary", ""), "kind": "drift"} for d in drift_items
    ]

    details = {
        "symbol": symbol.strip(),
        "class_symbol": class_symbol,
        "method": method,
        "contracts": contracts,
        "adrs": adrs,
        "known_gaps": gap_docs,
        "test_anchors": test_items,
        "drift_findings": drift_items,
        "code_anchors": code_anchors,
        "documentation_impact": doc_impact,
        "risk": risk,
        "risk_config": {
            k: preflight_cfg.get(k)
            for k in (
                "high_min_score",
                "medium_min_score",
                "gap_weight",
                "no_tests_weight",
                "drift_weight",
                "soft_block_enabled",
                "soft_block_require",
            )
        },
        "recommendation": recommendation,
        "provenance": {
            "sources_consulted": _source_refs(_dedupe_doc_refs(all_refs)),
            "retrieval_strategy": "preflight: impact_analysis + related_tests + drift index + documentation_impact",
        },
    }
    if doc_impact.get("state") != STATE_NONE:
        details["documentation_impact_text"] = format_documentation_impact(doc_impact)

    return {
        "card": card,
        "agent_policy": agent_policy,
        "details": details,
    }, None
