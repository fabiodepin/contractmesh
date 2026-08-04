#!/usr/bin/env python3
"""Map document kinds and statuses to source_type and trust_level."""

from __future__ import annotations

TRUST_RANK = {
    "confirmed": 70,
    "accepted": 60,
    "draft": 55,
    "known_risk": 50,
    "detected_mismatch": 45,
    "implementation": 40,
    "inferred": 20,
    "suggestion": 10,
}

KIND_DEFAULTS: dict[str, tuple[str, str]] = {
    "contract": ("contract", "confirmed"),
    "request_flow": ("contract", "confirmed"),
    "frontend_contract": ("contract", "confirmed"),
    "backend_contract": ("contract", "confirmed"),
    "adr": ("adr", "accepted"),
    "known_gaps": ("known_gap", "known_risk"),
    "code_anchor": ("code_anchor", "implementation"),
    "test_anchor": ("test_anchor", "implementation"),
    "openapi_spec": ("openapi", "inferred"),
    "architecture": ("contract", "confirmed"),
    "integrations": ("contract", "confirmed"),
    "agents": ("contract", "confirmed"),
    "workspace_doc": ("contract", "confirmed"),
    "doc": ("contract", "confirmed"),
    "touchpoint": ("contract", "confirmed"),
    "to_validate": ("contract", "draft"),
    "structural_edge": ("structural_graph", "inferred"),
    "drift": ("drift", "detected_mismatch"),
    "adapter": ("adapter", "inferred"),
    "git_mining": ("git_mining", "inferred"),
    "embedding": ("embedding", "suggestion"),
}


def trust_rank(trust_level: str) -> int:
    return TRUST_RANK.get(trust_level, 0)


def infer_trust(kind: str, status: str | None = None) -> tuple[str, str]:
    source_type, trust_level = KIND_DEFAULTS.get(kind, ("contract", "confirmed"))
    status_l = (status or "").strip().lower()
    if kind in ("contract", "request_flow", "frontend_contract", "backend_contract"):
        if status_l in ("draft", "proposed"):
            trust_level = "draft"
        elif status_l in ("confirmed", "active", "approved"):
            trust_level = "confirmed"
    elif kind == "adr":
        if status_l in ("draft", "proposed"):
            trust_level = "draft"
        elif status_l in ("accepted", "approved"):
            trust_level = "accepted"
    elif kind == "known_gaps":
        trust_level = "known_risk"
    return source_type, trust_level


def apply_trust_fields(doc: dict) -> dict:
    kind = str(doc.get("kind", "doc"))
    status = doc.get("status")
    source_type, trust_level = infer_trust(kind, status if isinstance(status, str) else None)
    doc["source_type"] = source_type
    doc["trust_level"] = trust_level
    return doc


def structural_edge(
    *,
    edge_type: str,
    source: str,
    target: str,
    repo: str,
    path: str | None = None,
    detail: str | None = None,
) -> dict:
    edge: dict = {
        "edge_type": edge_type,
        "source": source,
        "target": target,
        "repo": repo,
        "source_type": "structural_graph",
        "trust_level": "inferred",
    }
    if path:
        edge["path"] = path
    if detail:
        edge["detail"] = detail
    return edge
