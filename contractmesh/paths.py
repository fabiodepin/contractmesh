"""Package and repository path resolution."""

from __future__ import annotations

import os
from pathlib import Path


def package_root() -> Path:
    """Installed contractmesh package directory (contains engine/, templates/, mcp/)."""
    return Path(__file__).resolve().parent


def templates_dir() -> Path:
    return package_root() / "templates"


def source_checkout_root() -> Path | None:
    """ContractMesh git checkout root, or None when running from an installed wheel.

    Ignores CONTRACTMESH_TOOL_ROOT so maintainer release checks cannot be pointed at
    a checkout while executing an unrelated wheel install. Requires an editable-style
    layout (``contractmesh/`` package directory inside the checkout).
    """
    pkg = package_root()
    for candidate in (pkg.parent, *pkg.parents):
        if not (candidate / "pyproject.toml").is_file():
            continue
        if not (candidate / "tests" / "fixtures" / "basic-workspace").is_dir():
            continue
        if not (candidate / "scripts" / "lib").is_dir():
            continue
        package_in_tree = (candidate / "contractmesh").resolve()
        resolved_pkg = pkg.resolve()
        if resolved_pkg == package_in_tree or resolved_pkg.is_relative_to(package_in_tree):
            return candidate
    return None


def repo_root() -> Path:
    """Source checkout root (pyproject.toml) or CONTRACTMESH_TOOL_ROOT override."""
    env = os.environ.get("CONTRACTMESH_TOOL_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    checkout = source_checkout_root()
    if checkout is not None:
        return checkout
    return package_root().parent


def tool_root() -> Path:
    """Backward-compatible alias used by maintainer tooling and tests."""
    return repo_root()
