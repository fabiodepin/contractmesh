#!/usr/bin/env python3
"""Build evolution links from git history and indexed docs."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _git_log_paths(workspace: Path, rel_path: str, limit: int = 5) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "log", "--format=%H", "-n", str(limit), "--", rel_path],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def build_evolution_links(workspace: Path, manifest: dict) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for doc in manifest.get("documents", []):
        kind = doc.get("kind")
        path = doc.get("path")
        external_id = doc.get("external_id")
        if not path or not external_id:
            continue
        if kind == "contract":
            trust = ("contract", doc.get("trust_level", "confirmed"))
        elif kind == "adr":
            trust = ("adr", doc.get("trust_level", "accepted"))
        elif kind == "test_anchor":
            trust = ("test_anchor", "implementation")
        else:
            continue

        commits = _git_log_paths(workspace, path)
        if commits:
            links.append(
                {
                    "link_type": "introduced_in",
                    "source": external_id,
                    "target": commits[-1],
                    "repo": doc.get("repo"),
                    "path": path,
                    "source_type": trust[0],
                    "trust_level": trust[1],
                }
            )
            if len(commits) > 1:
                links.append(
                    {
                        "link_type": "modified_by",
                        "source": external_id,
                        "target": commits[0],
                        "repo": doc.get("repo"),
                        "path": path,
                        "source_type": "git_mining",
                        "trust_level": "inferred",
                    }
                )

        if kind == "adr":
            for contract_id in doc.get("related_contracts") or []:
                links.append(
                    {
                        "link_type": "decided_in",
                        "source": contract_id,
                        "target": external_id,
                        "repo": doc.get("repo"),
                        "path": path,
                        "source_type": "adr",
                        "trust_level": doc.get("trust_level", "accepted"),
                    }
                )

        if kind == "test_anchor" and doc.get("symbol"):
            for contract in manifest.get("documents", []):
                if contract.get("kind") != "contract":
                    continue
                anchors = contract.get("related_anchors") or []
                symbol = doc.get("symbol", "")
                if any(symbol.startswith(a.split(".")[0]) for a in anchors):
                    links.append(
                        {
                            "link_type": "validated_by",
                            "source": contract.get("external_id"),
                            "target": symbol,
                            "repo": doc.get("repo"),
                            "path": doc.get("path"),
                            "source_type": "test_anchor",
                            "trust_level": "implementation",
                        }
                    )
    return links
