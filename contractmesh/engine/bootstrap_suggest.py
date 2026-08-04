#!/usr/bin/env python3
"""Suggest draft contracts/ADRs/gaps from structural graph and anchors (never confirmed)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .workspace_paths import workspace_layout


def _controller_services(edges: list[dict]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for edge in edges:
        if edge.get("edge_type") != "uses_service":
            continue
        out.setdefault(edge["source"], set()).add(edge["target"])
    return out


def suggest_bootstrap(
    workspace: Path,
    manifest: dict,
    *,
    repo_filter: str | None = None,
) -> dict[str, Any]:
    edges = manifest.get("structural_edges") or []
    if repo_filter:
        edges = [e for e in edges if e.get("repo") == repo_filter]

    controllers = _controller_services(edges)
    contracts: list[dict] = []
    for controller, services in sorted(controllers.items()):
        contract_id = f"DRAFT-{controller.upper().replace('CONTROLLER', '')}-001"
        contracts.append(
            {
                "id": contract_id,
                "status": "draft",
                "trust_level": "draft",
                "title": f"{controller} HTTP surface (suggested)",
                "related_anchors": [controller, *sorted(services)],
            }
        )

    adrs = [
        {
            "id": "DRAFT-ADR-MT-001",
            "status": "draft",
            "trust_level": "draft",
            "title": "Multi-tenant schema-per-tenant (suggested)",
        },
        {
            "id": "DRAFT-ADR-AUTH-001",
            "status": "draft",
            "trust_level": "draft",
            "title": "Stateless JWT authentication (suggested)",
        },
    ]
    gaps = [
        {
            "id": "DRAFT-KG-001",
            "status": "draft",
            "trust_level": "draft",
            "summary": "Review enforcement gaps detected in services (suggested)",
        }
    ]

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_filter": repo_filter,
        "contracts": contracts,
        "adrs": adrs,
        "gaps": gaps,
        "owner_default": {"team": "TODO", "service": repo_filter or "TODO"},
        "note": "Draft-only suggestions. Human review required before --apply.",
    }


def write_bootstrap_suggestions(workspace: Path, payload: dict[str, Any]) -> Path:
    out_dir = workspace_layout(workspace).bootstrap_suggestions_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "suggestions.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path
