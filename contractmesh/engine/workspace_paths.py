#!/usr/bin/env python3
"""Workspace and tool path resolution for ContractMesh."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

WORKSPACE_NOT_FOUND_MSG = "ContractMesh workspace not found. Run: contractmesh init --here"
INDEX_BUILD_HINT = "contractmesh index"


@dataclass(frozen=True)
class WorkspaceLayout:
    workspace: Path
    index_dir: Path
    generated_dir: Path
    cache_dir: Path
    mcp_dir: Path

    @property
    def manifest_path(self) -> Path:
        return self.index_dir / "search-index.manifest.json"

    @property
    def local_index_path(self) -> Path:
        return self.index_dir / "search-index.local.json"

    @property
    def chunks_dir(self) -> Path:
        return self.index_dir / "chunks"

    @property
    def bootstrap_suggestions_dir(self) -> Path:
        return self.generated_dir / "bootstrap-suggestions"


from contractmesh.paths import tool_root as _paths_tool_root


def tool_root() -> Path:
    return _paths_tool_root()


def _workspace_markers(path: Path) -> bool:
    return (path / "contractmesh.yml").is_file() or (path / ".contractmesh").is_dir()


def find_workspace(start: Path | None = None) -> Path | None:
    env = os.environ.get("CONTRACTMESH_WORKSPACE", "").strip()
    if not env:
        env = os.environ.get("WORKSPACE_ROOT", "").strip()
    if env:
        path = Path(env).resolve()
        return path if _workspace_markers(path) else None

    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if _workspace_markers(candidate):
            return candidate
    return None


def require_workspace(start: Path | None = None) -> Path:
    workspace = find_workspace(start)
    if workspace is None:
        raise FileNotFoundError(WORKSPACE_NOT_FOUND_MSG)
    return workspace


def workspace_layout(workspace: Path) -> WorkspaceLayout:
    root = workspace.resolve()
    base = root / ".contractmesh"
    return WorkspaceLayout(
        workspace=root,
        index_dir=base / "index",
        generated_dir=base / "generated",
        cache_dir=base / "cache",
        mcp_dir=base / "mcp",
    )


def ensure_workspace_dirs(workspace: Path) -> WorkspaceLayout:
    layout = workspace_layout(workspace)
    for path in (
        layout.index_dir,
        layout.generated_dir,
        layout.cache_dir,
        layout.mcp_dir,
        layout.chunks_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return layout


def chunk_rel_path(layout: WorkspaceLayout, chunk_repo: str, slug: str) -> str:
    return f".contractmesh/index/chunks/{chunk_repo}/{slug}.jsonl"


def relative_to_workspace(workspace: Path, path: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()
