#!/usr/bin/env python3
"""Build a minimal structural graph: imports, routes, service/repository usage."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from .index_policy import IndexPolicy, load_index_policy
from .trust_metadata import structural_edge

JAVA_SRC = re.compile(r"\.java$")
TS_SRC = re.compile(r"\.(tsx?)$")

IMPORT_JAVA = re.compile(r"^import\s+(?:static\s+)?([\w.]+(?:\.\*)?);")
CLASS_JAVA = re.compile(r"(?:public\s+)?(?:abstract\s+)?class\s+(\w+)")
REST_CONTROLLER = re.compile(r"@RestController")
REQUEST_MAPPING = re.compile(r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?"([^"]+)"')
GET_MAPPING = re.compile(r'@(?:Get|Post|Put|Patch|Delete)Mapping\s*\(\s*(?:value\s*=\s*)?"([^"]+)"')
FIELD_SERVICE = re.compile(
    r"private\s+final\s+(\w+Service\w*)\s+(\w+);|"
    r"@Autowired\s+private\s+(\w+Service\w*)\s+(\w+);"
)
FIELD_REPOSITORY = re.compile(
    r"private\s+final\s+(\w+Repository\w*)\s+(\w+);|"
    r"@Autowired\s+private\s+(\w+Repository\w*)\s+(\w+);"
)

IMPORT_TS = re.compile(r"""from\s+['"]([^'"]+)['"]""")
ROUTE_PATH = re.compile(r"""<Route\s+[^>]*path=["']([^"']+)["']""")
ROUTE_ELEMENT = re.compile(
    r"""<Route\s+[^>]*path=["']([^"']+)["'][^>]*element=\{<(\w+)\s*/>\}"""
)
NESTED_ROUTE = re.compile(
    r"""<Route\s+[^>]*path=["']([^"']+)["'][^>]*element=\{<(\w+)\s*/>\}"""
)


def _simple_name(import_path: str) -> str:
    return import_path.rsplit(".", 1)[-1].replace(".*", "")


def _join_paths(base: str, sub: str) -> str:
    base = base.rstrip("/") or ""
    if not sub.startswith("/"):
        sub = "/" + sub
    if base == "":
        return sub
    return (base + sub).replace("//", "/")


def scan_java_file(path: Path, repo: str) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.as_posix()
    edges: list[dict] = []
    class_name: str | None = None
    m_class = CLASS_JAVA.search(text)
    if m_class:
        class_name = m_class.group(1)

    imports: list[str] = []
    for line in text.splitlines():
        m = IMPORT_JAVA.match(line.strip())
        if m:
            imports.append(m.group(1))

    if class_name:
        for imp in imports:
            target = _simple_name(imp)
            if target and target != class_name:
                edges.append(
                    structural_edge(
                        edge_type="imports",
                        source=class_name,
                        target=target,
                        repo=repo,
                        path=rel,
                    )
                )

    if class_name and REST_CONTROLLER.search(text):
        base_path = ""
        m_base = REQUEST_MAPPING.search(text)
        if m_base:
            base_path = m_base.group(1)
        routes = [m.group(1) for m in GET_MAPPING.finditer(text)]
        if not routes and base_path:
            routes = [""]
        for route in routes:
            full = _join_paths(base_path, route) if route != base_path else base_path or "/"
            edges.append(
                structural_edge(
                    edge_type="implements_route",
                    source=class_name,
                    target=full,
                    repo=repo,
                    path=rel,
                    detail="http",
                )
            )

    if class_name:
        for m in FIELD_SERVICE.finditer(text):
            service = m.group(1) or m.group(3)
            if service:
                edges.append(
                    structural_edge(
                        edge_type="uses_service",
                        source=class_name,
                        target=service,
                        repo=repo,
                        path=rel,
                    )
                )
        for m in FIELD_REPOSITORY.finditer(text):
            repository = m.group(1) or m.group(3)
            if repository:
                edges.append(
                    structural_edge(
                        edge_type="uses_repository",
                        source=class_name,
                        target=repository,
                        repo=repo,
                        path=rel,
                    )
                )

    if class_name and class_name.endswith("Service"):
        for m in FIELD_REPOSITORY.finditer(text):
            repository = m.group(1) or m.group(3)
            if repository:
                edges.append(
                    structural_edge(
                        edge_type="uses_repository",
                        source=class_name,
                        target=repository,
                        repo=repo,
                        path=rel,
                    )
                )

    return edges


def scan_ts_routes(path: Path, repo: str) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.as_posix()
    edges: list[dict] = []
    for m in ROUTE_ELEMENT.finditer(text):
        route, component = m.group(1), m.group(2)
        edges.append(
            structural_edge(
                edge_type="implements_route",
                source=component,
                target=route,
                repo=repo,
                path=rel,
                detail="spa",
            )
        )
    for m in IMPORT_TS.finditer(text):
        module = m.group(1)
        if module.startswith("@/pages/"):
            page = module.rsplit("/", 1)[-1]
            edges.append(
                structural_edge(
                    edge_type="imports",
                    source=path.stem,
                    target=page,
                    repo=repo,
                    path=rel,
                )
            )
    return edges


def collect_structural_edges(
    workspace: Path,
    repo_specs: Iterable[tuple[str, str]],
    policy: IndexPolicy | None = None,
) -> list[dict]:
    import os

    edges: list[dict] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    policy = policy or load_index_policy(workspace)
    for repo_name, rel_path in repo_specs:
        base = workspace / rel_path
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            policy.prune_walk_dirs(Path(dirpath), dirnames)
            for name in filenames:
                path = Path(dirpath) / name
                rel = path.relative_to(workspace).as_posix()
                if policy.ignores(rel):
                    continue
                file_edges: list[dict] = []
                if JAVA_SRC.search(path.name):
                    file_edges = scan_java_file(path, repo_name)
                elif path.name == "main.tsx":
                    file_edges = scan_ts_routes(path, repo_name)
                for edge in file_edges:
                    key = (
                        edge["edge_type"],
                        edge["source"],
                        edge["target"],
                        edge["repo"],
                        edge.get("path", ""),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append(edge)
    return edges
