#!/usr/bin/env python3
"""Export .contractmesh/index/search-index.manifest.json as a deterministic graph."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .workspace_paths import INDEX_BUILD_HINT, workspace_layout

GRAPH_VERSION = 1


def node_id(doc: dict[str, Any]) -> str:
    return str(doc.get("external_id") or doc.get("id"))


def add_node(nodes: dict[str, dict[str, Any]], id_: str, type_: str, label: str, **extra: Any) -> None:
    if not id_:
        return
    item = {"id": id_, "type": type_, "label": label}
    item.update({k: v for k, v in extra.items() if v not in (None, "", [], {})})
    nodes.setdefault(id_, item)


def add_edge(edges: set[tuple[str, str, str]]) -> None:
    pass


def export_graph(workspace: Path) -> dict[str, Any]:
    manifest_path = workspace_layout(workspace).manifest_path
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"{manifest_path.relative_to(workspace)} not found; run {INDEX_BUILD_HINT}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    docs = manifest.get("documents", [])
    by_id = {d.get("id"): d for d in docs}
    by_external = {d.get("external_id"): d for d in docs if d.get("external_id")}
    nodes: dict[str, dict[str, Any]] = {}
    edges: set[tuple[str, str, str]] = set()

    code_symbols: dict[str, dict] = {}
    test_docs: list[dict] = []

    for doc in docs:
        kind = doc.get("kind")
        if kind not in {"contract", "adr", "known_gaps", "code_anchor", "test_anchor"}:
            continue
        nid = node_id(doc)
        add_node(nodes, nid, kind, doc.get("title") or doc.get("symbol") or nid, path=doc.get("path"), repo=doc.get("repo"))
        repo = doc.get("repo")
        if repo:
            add_node(nodes, repo, "service", repo)
            edges.add((nid, repo, "belongs_to_service"))
        owner = doc.get("owner")
        if isinstance(owner, dict):
            owner_id = f"owner:{owner.get('team') or owner.get('contact') or owner.get('service')}"
            add_node(nodes, owner_id, "owner", owner.get("team") or owner_id, **owner)
            edges.add((nid, owner_id, "owned_by"))
        for gap in doc.get("known_gap_ids") or []:
            add_node(nodes, gap, "known_gap", gap)
            edges.add((nid, gap, "mentions_gap"))
        if kind == "code_anchor" and doc.get("symbol"):
            code_symbols[str(doc["symbol"]).lower()] = doc
        if kind == "test_anchor":
            test_docs.append(doc)

    for doc in docs:
        source = node_id(doc)
        for anchor_id in doc.get("code_anchors") or []:
            anchor = by_id.get(anchor_id)
            if anchor:
                edges.add((source, node_id(anchor), "implemented_by"))
        for contract_id in doc.get("related_contracts") or []:
            target = by_external.get(contract_id)
            if target:
                edges.add((source, node_id(target), "relates_to"))

    for test in test_docs:
        haystack = f"{test.get('symbol','')} {test.get('path','')}".lower()
        for symbol, code_doc in code_symbols.items():
            if symbol and symbol in haystack:
                edges.add((node_id(code_doc), node_id(test), "tested_by"))

    for edge in manifest.get("structural_edges") or []:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        etype = edge.get("edge_type", "structural")
        if src and tgt:
            add_node(nodes, src, "structural", src, repo=edge.get("repo"))
            add_node(nodes, tgt, "structural", tgt, repo=edge.get("repo"))
            edges.add((src, tgt, etype))

    for link in manifest.get("evolution_links") or []:
        src = link.get("source", "")
        tgt = link.get("target", "")
        ltype = link.get("link_type", "evolution")
        if src and tgt:
            edges.add((src, tgt, ltype))

    return {
        "graph_version": GRAPH_VERSION,
        "schema_version": manifest.get("schema_version"),
        "workspace_mapping_version": manifest.get("workspace_mapping_version"),
        "nodes": sorted(nodes.values(), key=lambda n: (n["type"], n["id"])),
        "edges": [
            {"from": f, "to": t, "type": ty}
            for f, t, ty in sorted(edges, key=lambda e: (e[2], e[0], e[1]))
        ],
    }


def main(argv: list[str]) -> int:
    workspace = Path(argv[1] if len(argv) > 1 else ".").resolve()
    print(json.dumps(export_graph(workspace), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
