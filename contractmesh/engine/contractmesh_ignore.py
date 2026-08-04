#!/usr/bin/env python3
"""ContractMesh ignore-file support."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

# Baseline denylist when .contractmeshignore is missing or incomplete.
# Workspaces should still ship a full .contractmeshignore from init templates.
DEFAULT_IGNORE_PATTERNS = (
    # Secrets and credentials
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.crt",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "*.kdb",
    "*.asc",
    "*.gpg",
    "secrets/",
    "credentials/",
    "vault/",
    "private/",
    "keys/",
    # Cloud credentials
    ".aws/",
    ".azure/",
    ".gcp/",
    ".config/gcloud/",
    "*.tfvars",
    "terraform.tfstate*",
    "*.tfstate.*",
    # Kubernetes and containers
    "kubeconfig",
    ".kube/",
    "docker-compose.override.yml",
    # CI/CD secrets
    ".github/workflows/*.secrets.yml",
    ".gitlab-ci*.local.yml",
    # Package manager auth
    ".npmrc",
    ".yarnrc",
    ".pypirc",
    ".poetry.toml",
    "pip.conf",
    # SSH
    ".ssh/",
    "id_rsa",
    "id_ed25519",
    "known_hosts",
    # Build artifacts
    "node_modules/",
    "dist/",
    "build/",
    "target/",
    "coverage/",
    ".cache/",
    ".next/",
    ".nuxt/",
    ".gradle/",
    "out/",
    # Python
    ".venv/",
    "venv/",
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    ".pytest_cache/",
    # Java
    ".mvn/",
    "*.class",
    # IDE and logs
    ".idea/",
    ".vscode/",
    ".DS_Store",
    "*.log",
    # ContractMesh internals
    ".contractmesh/index/",
    ".contractmesh/cache/",
    ".contractmesh/generated/",
)


@dataclass(frozen=True)
class ContractMeshIgnore:
    """Small gitignore-like matcher for the local ContractMesh index."""

    workspace: Path
    patterns: tuple[str, ...]

    def ignores(self, path: Path | str) -> bool:
        rel = self._normalize(path)
        parts = rel.split("/")
        for pattern in self.patterns:
            if self._matches(pattern, rel, parts):
                return True
        return False

    def _normalize(self, path: Path | str) -> str:
        raw = Path(path)
        if raw.is_absolute():
            try:
                raw = raw.relative_to(self.workspace)
            except ValueError:
                pass
        return raw.as_posix().strip("/")

    @staticmethod
    def _matches(pattern: str, rel: str, parts: list[str]) -> bool:
        pat = pattern.strip().replace("\\", "/").strip("/")
        if not pat or pat.startswith("#"):
            return False
        if pattern.strip().endswith("/"):
            return pat in parts or rel.startswith(f"{pat}/") or f"/{pat}/" in f"/{rel}/"
        if "/" in pat:
            return fnmatch.fnmatch(rel, pat) or rel == pat
        return any(fnmatch.fnmatch(part, pat) for part in parts)


def load_contractmesh_ignore(workspace: Path) -> ContractMeshIgnore:
    """Load .contractmeshignore from the workspace root."""
    path = workspace / ".contractmeshignore"
    patterns = list(DEFAULT_IGNORE_PATTERNS)
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                patterns.append(stripped)
    return ContractMeshIgnore(workspace=workspace.resolve(), patterns=tuple(patterns))
