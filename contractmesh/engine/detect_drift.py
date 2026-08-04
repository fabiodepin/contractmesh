#!/usr/bin/env python3
"""Detect contract vs implementation drift (structural checks)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Relative paths checked under each indexed repo for a typed HTTP client module.
# Keep this list framework-agnostic; projects may use any one of these names.
FRONTEND_CLIENT_CANDIDATES = (
    "src/lib/api-client.ts",
    "src/lib/api-services.ts",
    "src/lib/http.ts",
    "src/lib/client.ts",
    "src/api/client.ts",
    "src/api/api-client.ts",
    "src/api/index.ts",
    "lib/api-client.ts",
    "lib/api-services.ts",
    "lib/http.ts",
)


def _find_frontend_api_client(workspace: Path, manifest: dict) -> Path | None:
    repos = manifest.get("repos") or []
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        rel = str(repo.get("path", "")).strip().rstrip("/")
        if not rel or rel in (".", "./"):
            # Workspace-root "repo" rarely holds the SPA; skip.
            continue
        base = workspace / rel
        for candidate_rel in FRONTEND_CLIENT_CANDIDATES:
            candidate = base / candidate_rel
            if candidate.is_file():
                return candidate
    # Fallback: any indexed path that looks like an HTTP client module
    for doc in manifest.get("documents") or []:
        path = str(doc.get("path") or "")
        name = Path(path).name.lower()
        if name in {
            "api-services.ts",
            "api-client.ts",
            "http.ts",
            "client.ts",
        } or path.endswith(("/api/client.ts", "/api/index.ts")):
            full = workspace / path
            if full.is_file():
                return full
    return None


def detect_drift(
    workspace: Path,
    manifest: dict,
    *,
    openapi_enabled: bool = False,
    frontend_backend: bool = False,
) -> list[dict[str, Any]]:
    """Return drift findings with trust_level detected_mismatch."""
    findings: list[dict[str, Any]] = []
    build_stats = manifest.get("build_stats") or {}
    unresolved = build_stats.get("contract_symbols_unresolved_unique") or []
    if isinstance(unresolved, int):
        count = unresolved
        if count > 0:
            findings.append(
                {
                    "drift_type": "anchor_unresolved",
                    "summary": f"{count} contract anchor symbol(s) unresolved in indexed repos",
                    "source_type": "drift",
                    "trust_level": "detected_mismatch",
                }
            )
    elif isinstance(unresolved, list):
        for symbol in unresolved:
            findings.append(
                {
                    "drift_type": "anchor_unresolved",
                    "summary": f"Contract references anchor '{symbol}' not found in code index",
                    "source_type": "drift",
                    "trust_level": "detected_mismatch",
                }
            )

    if openapi_enabled:
        openapi_count = sum(
            1 for d in manifest.get("documents", []) if d.get("kind") == "openapi_spec"
        )
        if openapi_count == 0:
            findings.append(
                {
                    "drift_type": "contract_vs_openapi",
                    "summary": "OpenAPI drift check enabled but no specs indexed under .contractmesh/generated/openapi/",
                    "source_type": "drift",
                    "trust_level": "detected_mismatch",
                }
            )

    if frontend_backend:
        api_services = _find_frontend_api_client(workspace, manifest)
        if api_services is None:
            findings.append(
                {
                    "drift_type": "contract_vs_frontend",
                    "summary": "typed frontend HTTP client module not found for client/server path comparison",
                    "source_type": "drift",
                    "trust_level": "detected_mismatch",
                }
            )

    return findings


def write_drift_suggestions(workspace: Path, findings: list[dict[str, Any]]) -> Path | None:
    if not findings:
        return None
    out_dir = workspace / ".contractmesh" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "drift-suggestions.md"
    lines = ["# Drift suggestions (generated)", ""]
    for item in findings:
        lines.append(f"- **{item.get('drift_type')}**: {item.get('summary')}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path
