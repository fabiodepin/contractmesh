#!/usr/bin/env python3
"""Build local RAG index: manifest, local metadata, and chunk JSONL files."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Any

from .build_code_anchors import collect_code_anchors
from .chunk_ids import chunk_id_for
from .build_contract_crosslinks import CROSSLINK_SOURCE_KINDS, apply_contract_crosslinks
from .index_policy import IndexPolicy, load_index_policy
from .workspace_manifest import load_workspace_manifest
from .trust_metadata import apply_trust_fields
from .build_structural_graph import collect_structural_edges
from .detect_drift import detect_drift, write_drift_suggestions
from .build_evolution_graph import build_evolution_links
from .workspace_paths import chunk_rel_path, ensure_workspace_dirs, workspace_layout

try:
    from .adapters.null_adapter import load_edges as load_null_adapter_edges
except ImportError:
    def load_null_adapter_edges(*_a, **_k):  # type: ignore[misc]
        return []

# This intentionally accepts non-gap codes with similar shape in v1.
GAP_ID_RE = re.compile(r"\b[A-Z]{2,5}(?:-[A-Z0-9]+){1,5}-[0-9]{2,}\b")

WORKSPACE_REPO = os.environ.get("WORKSPACE_REPO", "contractmesh")
SCHEMA_VERSION = 3
CHUNK_STRATEGY = "markdown-heading-v1"
SINGLE_CHUNK_BYTES = 8 * 1024
CHUNK_TARGET_BYTES = 2 * 1024
MAX_HEADINGS = 20
MAX_KEYWORDS = 30
SNIPPET_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
FRONT_MATTER_BOUNDARY = "---"

WEIGHT_BY_KIND = {
    "agents": 100,
    "known_gaps": 90,
    "to_validate": 85,
    "contract": 80,
    "request_flow": 75,
    "frontend_contract": 75,
    "backend_contract": 75,
    "architecture": 70,
    "integrations": 70,
    "adr": 68,
    "touchpoint": 65,
    "workspace_doc": 60,
    "code_anchor": 58,
    "test_anchor": 57,
    "doc": 55,
    "openapi_spec": 50,
}

KNOWN_KIND_BY_BASENAME = {
    "agents.md": "agents",
    "known-gaps.md": "known_gaps",
    "architecture.md": "architecture",
    "integrations.md": "integrations",
    "request-flow.md": "request_flow",
    "frontend-contract.md": "frontend_contract",
    "backend-contract.md": "backend_contract",
    "to-validate.md": "to_validate",
    "touchpoints.md": "touchpoint",
}


@dataclass(frozen=True)
class RepoSpec:
    name: str
    rel_path: str


def parse_repo_spec(raw: str) -> RepoSpec:
    """Parse repo specs from contractmesh.yml repos list.

    Supported formats:
    - app
    - app=example-app
    - example-app (repo name becomes basename when name omitted)
    """
    value = raw.strip()
    if "=" in value:
        name, rel_path = value.split("=", 1)
        return RepoSpec(name=name.strip(), rel_path=rel_path.strip().strip("/"))
    rel_path = value.strip().strip("/")
    return RepoSpec(name=Path(rel_path).name, rel_path=rel_path)


def load_roles(repositories_md: Path) -> dict[str, str]:
    roles: dict[str, str] = {}
    if not repositories_md.is_file():
        return roles
    text = repositories_md.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        m = re.match(r"^\|\s+\*\*([^*]+)\*\*\s+\|\s+([^|]+)\s+\|", line)
        if m:
            roles[m.group(1).strip()] = m.group(2).strip()
    return roles


def is_known_gap_id(gap_id: str) -> bool:
    """Keep gap-like IDs; drop ADR/CONTRACT ids that also match GAP_ID_RE.

    GAP_ID_RE intentionally matches dotted product ids (e.g. FOO-BAR-001). Contract
    ids like FOO-AUTH-CONTRACT-001 also match that pattern, so exclude them here
    instead of requiring a project-specific ``-KG-`` infix.
    """
    if not gap_id or gap_id.startswith("ADR-"):
        return False
    if "-CONTRACT-" in gap_id:
        return False
    return True


def gap_ids_from_text(text: str) -> list[str]:
    return sorted(g for g in set(GAP_ID_RE.findall(text)) if is_known_gap_id(g))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return f"sha256:{h.hexdigest()}"


def parse_markdown_meta(text: str, fallback_title: str) -> tuple[str, list[str]]:
    title = fallback_title
    headings: list[str] = []
    for line in text.splitlines():
        m = SNIPPET_HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        heading = m.group(2).strip()
        if level == 1 and title == fallback_title:
            title = heading
        if level <= 3:
            headings.append(heading)
        if len(headings) >= MAX_HEADINGS:
            break
    return title, headings[:MAX_HEADINGS]


def parse_front_matter(text: str) -> tuple[dict, str]:
    """Parse a small YAML-like front matter subset without external deps."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONT_MATTER_BOUNDARY:
        return {}, text
    end_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == FRONT_MATTER_BOUNDARY:
            end_idx = i
            break
    if end_idx is None:
        return {}, text

    meta: dict = {}
    current_key: str | None = None
    for raw in lines[1:end_idx]:
        if not raw.strip():
            continue
        if raw.startswith((" ", "\t")):
            if not current_key:
                continue
            stripped = raw.strip()
            if stripped.startswith("- "):
                if not isinstance(meta.get(current_key), list):
                    meta[current_key] = []
                meta[current_key].append(stripped[2:].strip())
            elif ":" in stripped:
                k, v = stripped.split(":", 1)
                if not isinstance(meta.get(current_key), dict):
                    meta[current_key] = {}
                meta[current_key][k.strip()] = v.strip()
            continue
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        current_key = key.strip()
        value = value.strip()
        if value:
            meta[current_key] = value
        else:
            meta[current_key] = []

    body = "\n".join(lines[end_idx + 1 :]).lstrip()
    return meta, body


def curated_keywords(
    repo: str, kind: str, domain: str | None, title: str
) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    def add(token: str) -> None:
        t = token.strip().lower()
        if not t or len(t) < 2 or t in seen:
            return
        seen.add(t)
        out.append(t)

    add(repo)
    add(kind)
    if domain:
        add(domain)
    for part in re.split(r"[^a-zA-Z0-9]+", title):
        add(part)
    return out[:MAX_KEYWORDS]


def add_metadata_keywords(keywords: list[str], meta: dict) -> list[str]:
    seen = set(keywords)
    out = list(keywords)

    def add(value: object) -> None:
        if not isinstance(value, str):
            return
        for part in re.split(r"[^a-zA-Z0-9@.]+", value):
            token = part.strip().lower()
            if len(token) < 2 or token in seen:
                continue
            seen.add(token)
            out.append(token)

    for key in ("id", "status"):
        add(meta.get(key))
    owner = meta.get("owner")
    if isinstance(owner, dict):
        for value in owner.values():
            add(value)
    for key in ("related_contracts", "related_anchors"):
        value = meta.get(key)
        if isinstance(value, list):
            for item in value:
                add(item)
    return out[:MAX_KEYWORDS]


def infer_kind(rel_path: str, basename: str, is_workspace: bool) -> str:
    lower = basename.lower()
    if lower in KNOWN_KIND_BY_BASENAME:
        return KNOWN_KIND_BY_BASENAME[lower]
    norm = rel_path.replace("\\", "/").lower()
    if "/docs/adrs/" in norm and lower.endswith(".md"):
        return "adr"
    if "/contracts/" in norm and lower.endswith(".md") and lower != "readme.md":
        return "contract"
    if is_workspace:
        return "workspace_doc"
    return "doc"


def infer_domain(rel_path: str, kind: str) -> str | None:
    if kind in ("agents", "openapi_spec", "workspace_doc", "doc"):
        return None
    norm = rel_path.replace("\\", "/")
    if kind == "contract":
        return Path(norm).stem
    stem = Path(norm).stem
    if stem in ("README", "readme"):
        return None
    if stem in KNOWN_KIND_BY_BASENAME.values():
        return None
    return stem if stem else None


def doc_id_for(repo: str, rel_path: str, repo_root_rel: str | None = None) -> str:
    norm = rel_path.replace("\\", "/")
    if repo == WORKSPACE_REPO:
        slug = norm.replace("/", ":").replace(".md", "")
    else:
        prefix = f"{repo_root_rel or repo}/".replace("\\", "/")
        rest = norm[len(prefix) :] if norm.startswith(prefix) else norm
        slug = rest.replace("/", ":").replace(".md", "")
    return f"doc:{repo}:{slug}"


def chunk_slug_for(rel_path: str, repo: str, repo_root_rel: str | None = None) -> str:
    norm = rel_path.replace("\\", "/")
    if repo == WORKSPACE_REPO:
        rest = norm
    else:
        prefix = f"{repo_root_rel or repo}/".replace("\\", "/")
        rest = norm[len(prefix) :] if norm.startswith(prefix) else norm
    return rest.replace("/", "-").replace(".md", "")


def build_links(
    workspace: Path,
    repo: str,
    rel_path: str,
    kind: str,
    repo_root_rel: str | None = None,
) -> dict:
    links: dict = {"related": []}
    norm = rel_path.replace("\\", "/")
    if repo != WORKSPACE_REPO:
        root = repo_root_rel or repo
        agents = workspace / root / "AGENTS.md"
        if agents.is_file():
            links["agents"] = f"{root}/AGENTS.md"
        contracts_readme = workspace / root / "docs" / "ai" / "contracts" / "README.md"
        if (kind == "contract" or "/contracts/" in norm) and contracts_readme.is_file():
            links["contracts_readme"] = f"{root}/docs/ai/contracts/README.md"
    return links


def split_chunks(text: str, title: str, *, kind: str | None = None) -> list[dict]:
    """Split markdown; contract/known_gaps always split by ## (chunk ids may change on rebuild)."""
    force_sections = kind in ("contract", "known_gaps")
    encoded = text.encode("utf-8")
    if not force_sections and len(encoded) <= SINGLE_CHUNK_BYTES:
        return [{"heading": title, "text": text.strip()}]

    sections: list[tuple[str, str]] = []
    current_heading = title
    current_lines: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))

    if not sections:
        return [{"heading": title, "text": text.strip()}]

    chunks: list[dict] = []
    for heading, body in sections:
        if not body:
            continue
        if len(body.encode("utf-8")) <= CHUNK_TARGET_BYTES:
            chunks.append({"heading": heading, "text": body})
            continue
        paras = [p.strip() for p in body.split("\n\n") if p.strip()]
        buf: list[str] = []
        buf_len = 0
        for para in paras:
            plen = len(para.encode("utf-8"))
            if buf and buf_len + plen + 2 > CHUNK_TARGET_BYTES:
                chunks.append({"heading": heading, "text": "\n\n".join(buf)})
                buf = [para]
                buf_len = plen
            else:
                buf.append(para)
                buf_len += plen + (2 if buf_len else 0)
        if buf:
            chunks.append({"heading": heading, "text": "\n\n".join(buf)})

    return chunks or [{"heading": title, "text": text.strip()}]


def index_markdown_file(
    workspace: Path,
    abs_path: Path,
    rel_path: str,
    repo: str,
    roles: dict[str, str],
    chunks_root: Path,
    repo_root_rel: str | None = None,
) -> tuple[dict, dict, int]:
    raw_text = abs_path.read_text(encoding="utf-8", errors="replace")
    front_matter, text = parse_front_matter(raw_text)
    basename = abs_path.name
    is_workspace = repo == WORKSPACE_REPO
    kind = infer_kind(rel_path, basename, is_workspace)
    domain = infer_domain(rel_path, kind)
    title, headings = parse_markdown_meta(text, Path(basename).stem.replace("-", " ").title())
    if front_matter.get("title"):
        title = str(front_matter["title"])
    doc_id = doc_id_for(repo, rel_path, repo_root_rel=repo_root_rel)
    keywords = add_metadata_keywords(curated_keywords(repo, kind, domain, title), front_matter)
    gap_ids = gap_ids_from_text(text)
    links = build_links(workspace, repo, rel_path, kind, repo_root_rel=repo_root_rel)

    manifest_doc: dict = {
        "id": doc_id,
        "repo": repo,
        "path": rel_path.replace("\\", "/"),
        "kind": kind,
        "title": title,
        "headings": headings,
        "keywords": keywords,
        "known_gap_ids": gap_ids,
        "links": links,
        "weight": WEIGHT_BY_KIND.get(kind, 55),
        "chunking": {"strategy": CHUNK_STRATEGY},
        "embedding": {"status": "pending", "model": None, "dimensions": None},
    }
    if domain:
        manifest_doc["domain"] = domain
    if front_matter.get("id"):
        manifest_doc["external_id"] = str(front_matter["id"])
    if front_matter.get("status"):
        manifest_doc["status"] = str(front_matter["status"])
    owner = front_matter.get("owner")
    if isinstance(owner, dict):
        manifest_doc["owner"] = owner
    for key in ("related_contracts", "related_anchors"):
        value = front_matter.get(key)
        if isinstance(value, list):
            manifest_doc[key] = [str(v) for v in value]
    role = roles.get(repo) if repo != WORKSPACE_REPO else None
    if role:
        manifest_doc["role"] = role

    apply_trust_fields(manifest_doc)

    raw_chunks = split_chunks(text, title, kind=kind)
    slug = chunk_slug_for(rel_path, repo, repo_root_rel=repo_root_rel)
    chunk_repo = repo if repo != WORKSPACE_REPO else "_workspace"
    chunk_dir = chunks_root / chunk_repo
    chunk_dir.mkdir(parents=True, exist_ok=True)
    layout = workspace_layout(workspace)
    chunk_rel = chunk_rel_path(layout, chunk_repo, slug)
    chunk_abs = workspace / chunk_rel

    with chunk_abs.open("w", encoding="utf-8") as f:
        for i, ch in enumerate(raw_chunks):
            row = {
                "chunk_id": chunk_id_for(doc_id, i),
                "doc_id": doc_id,
                "title": title,
                "heading": ch["heading"],
                "text": ch["text"],
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    local_doc = {
        "id": doc_id,
        "content_hash": sha256_file(abs_path),
        "absolute_path": str(abs_path.resolve()),
        "chunk_count": len(raw_chunks),
        "chunk_path": chunk_rel.replace("\\", "/"),
    }

    return manifest_doc, local_doc, len(raw_chunks)


def collect_workspace_docs(
    workspace: Path,
    policy: IndexPolicy | None = None,
) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    policy = policy or load_index_policy(workspace)
    docs_dir = workspace / "docs"
    if not docs_dir.is_dir():
        return found
    for root, dirnames, files in os.walk(docs_dir):
        if "generated" in Path(root).parts:
            dirnames[:] = []
            continue
        policy.prune_walk_dirs(Path(root), dirnames)
        for name in files:
            if not name.endswith(".md"):
                continue
            abs_path = Path(root) / name
            rel = abs_path.relative_to(workspace).as_posix()
            if policy.ignores(rel):
                continue
            found.append((abs_path, rel))
    return found


def collect_repo_docs(
    workspace: Path,
    spec: RepoSpec,
    policy: IndexPolicy | None = None,
) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    policy = policy or load_index_policy(workspace)
    base = workspace / spec.rel_path
    if not base.is_dir():
        return found

    agents = base / "AGENTS.md"
    if agents.is_file():
        rel = agents.relative_to(workspace).as_posix()
        if not policy.ignores(rel):
            found.append((agents, rel))

    ai_dir = base / "docs" / "ai"
    if ai_dir.is_dir():
        for root, dirnames, files in os.walk(ai_dir):
            policy.prune_walk_dirs(Path(root), dirnames)
            for name in files:
                if not name.endswith(".md"):
                    continue
                abs_path = Path(root) / name
                rel = abs_path.relative_to(workspace).as_posix()
                if policy.ignores(rel):
                    continue
                found.append((abs_path, rel))
    adrs_dir = base / "docs" / "adrs"
    if adrs_dir.is_dir():
        for root, dirnames, files in os.walk(adrs_dir):
            policy.prune_walk_dirs(Path(root), dirnames)
            for name in files:
                if not name.endswith(".md"):
                    continue
                abs_path = Path(root) / name
                rel = abs_path.relative_to(workspace).as_posix()
                if policy.ignores(rel):
                    continue
                found.append((abs_path, rel))
    return found


OPENAPI_BASENAMES = (
    "openapi.json",
    "openapi.yaml",
    "openapi.yml",
    "swagger.json",
    "swagger.yaml",
    "swagger.yml",
    "api-docs.json",
)


def _index_openapi_file(
    workspace: Path,
    path: Path,
    *,
    repo: str,
    roles: dict[str, str],
    policy: IndexPolicy,
) -> tuple[dict, dict, int] | None:
    if not path.is_file():
        return None
    try:
        rel = path.relative_to(workspace).as_posix()
    except ValueError:
        return None
    if policy.ignores(rel):
        return None
    doc_id = doc_id_for(repo, rel)
    title = path.name
    manifest_doc = {
        "id": doc_id,
        "repo": repo,
        "path": rel,
        "kind": "openapi_spec",
        "title": title,
        "headings": [],
        "keywords": curated_keywords(repo, "openapi_spec", None, title),
        "known_gap_ids": [],
        "links": {"related": []},
        "weight": WEIGHT_BY_KIND["openapi_spec"],
        "chunking": {"strategy": CHUNK_STRATEGY},
        "embedding": {"status": "pending", "model": None, "dimensions": None},
    }
    if repo in roles:
        manifest_doc["role"] = roles[repo]
    apply_trust_fields(manifest_doc)
    text = path.read_text(encoding="utf-8", errors="replace")[:SINGLE_CHUNK_BYTES]
    slug = chunk_slug_for(rel, repo)
    layout = workspace_layout(workspace)
    chunk_rel = chunk_rel_path(layout, repo, slug)
    chunk_abs = workspace / chunk_rel
    chunk_abs.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "chunk_id": chunk_id_for(doc_id, 0),
        "doc_id": doc_id,
        "title": title,
        "heading": title,
        "text": text,
    }
    with chunk_abs.open("w", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    local_doc = {
        "id": doc_id,
        "content_hash": sha256_file(path),
        "absolute_path": str(path.resolve()),
        "chunk_count": 1,
        "chunk_path": chunk_rel,
    }
    return (manifest_doc, local_doc, 1)


def discover_openapi_source_files(
    workspace: Path,
    repo_specs: list[RepoSpec] | None = None,
    policy: IndexPolicy | None = None,
) -> list[tuple[str, Path]]:
    """Find common OpenAPI/Swagger filenames under workspace and configured repos."""
    policy = policy or load_index_policy(workspace)
    found: list[tuple[str, Path]] = []
    seen: set[str] = set()

    def consider(repo: str, path: Path) -> None:
        if not path.is_file():
            return
        try:
            rel = path.relative_to(workspace).as_posix()
        except ValueError:
            return
        if policy.ignores(rel) or rel in seen:
            return
        # Skip noisy build/vendor trees.
        parts = {p.lower() for p in path.parts}
        if parts & {"node_modules", ".git", "vendor", "dist", "build", "target"}:
            return
        seen.add(rel)
        found.append((repo, path))

    openapi_dir = workspace_layout(workspace).generated_dir / "openapi"
    if openapi_dir.is_dir():
        for path in sorted(openapi_dir.glob("*")):
            if not path.is_file():
                continue
            name = path.name
            repo = name.split("-", 1)[0] if "-" in name else "unknown"
            consider(repo, path)

    roots: list[tuple[str, Path]] = [("workspace", workspace)]
    for spec in repo_specs or []:
        roots.append((spec.name, workspace / spec.rel_path))

    for repo, root in roots:
        if not root.is_dir():
            continue
        for basename in OPENAPI_BASENAMES:
            # Shallow + one docs/ level — avoid full-tree walks for speed.
            consider(repo, root / basename)
            consider(repo, root / "docs" / basename)
            consider(repo, root / "api" / basename)
            consider(repo, root / "openapi" / basename)
            consider(repo, root / "src" / "main" / "resources" / basename)

    return found


def collect_openapi_specs(
    workspace: Path,
    roles: dict[str, str],
    repo_specs: list[RepoSpec] | None = None,
    policy: IndexPolicy | None = None,
) -> list[tuple[dict, dict, int]]:
    policy = policy or load_index_policy(workspace)
    out: list[tuple[dict, dict, int]] = []
    for repo, path in discover_openapi_source_files(workspace, repo_specs, policy=policy):
        indexed = _index_openapi_file(
            workspace, path, repo=repo, roles=roles, policy=policy
        )
        if indexed:
            out.append(indexed)
    return out


def read_mapping_version(workspace: Path) -> str:
    return str(load_workspace_manifest(workspace).get("workspace_mapping_version", "v1"))


def workspace_repo_label(manifest: dict[str, Any]) -> str:
    """Repo name for workspace-level docs (contractmesh.yml at root)."""
    env = os.environ.get("WORKSPACE_REPO", "").strip()
    if env:
        return env
    repos = manifest.get("repos") or []
    if len(repos) == 1:
        path = str(repos[0].get("path", "")).strip().strip("/")
        if path in ("", "."):
            return str(repos[0].get("name") or manifest.get("name") or "workspace")
    return str(manifest.get("name") or "workspace")


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: build_search_index.py <workspace_dir> <repo1,repo2,...>", file=sys.stderr)
        return 1

    workspace = Path(sys.argv[1]).resolve()
    repo_specs = [parse_repo_spec(r) for r in sys.argv[2].split(",") if r]
    layout = ensure_workspace_dirs(workspace)
    generated = layout.index_dir
    chunks_root = layout.chunks_dir
    if chunks_root.exists():
        shutil.rmtree(chunks_root)

    t0 = time.perf_counter()

    roles = load_roles(workspace / "docs" / "ai" / "repositories.md")
    mapping_version = read_mapping_version(workspace)
    ws_manifest = load_workspace_manifest(workspace)
    workspace_repo = workspace_repo_label(ws_manifest)
    index_flags = ws_manifest.get("index") or {}
    try:
        policy = load_index_policy(workspace, ws_manifest)
    except ValueError as exc:
        raise SystemExit(f"[FAIL] {exc}") from exc
    if policy.mode == "allowlist" and not policy.include:
        raise SystemExit(
            "[FAIL] index.mode=allowlist requires a non-empty index.include "
            "(fail-closed)"
        )

    manifest_docs: list[dict] = []
    local_docs: list[dict] = []
    total_chunks = 0

    for abs_path, rel in collect_workspace_docs(workspace, policy=policy):
        m, l, n = index_markdown_file(
            workspace, abs_path, rel, workspace_repo, roles, chunks_root
        )
        manifest_docs.append(m)
        local_docs.append(l)
        total_chunks += n

    for spec in repo_specs:
        for abs_path, rel in collect_repo_docs(workspace, spec, policy=policy):
            m, l, n = index_markdown_file(
                workspace,
                abs_path,
                rel,
                spec.name,
                roles,
                chunks_root,
                repo_root_rel=spec.rel_path,
            )
            manifest_docs.append(m)
            local_docs.append(l)
            total_chunks += n

    for m, l, n in collect_openapi_specs(workspace, roles, repo_specs, policy=policy):
        manifest_docs.append(m)
        local_docs.append(l)
        total_chunks += n

    anchor_entries, anchor_by_repo = collect_code_anchors(
        workspace,
        [f"{s.name}={s.rel_path}" for s in repo_specs],
        chunks_root,
        roles,
        weight=WEIGHT_BY_KIND["code_anchor"],
        policy=policy,
    )
    for m, l, n in anchor_entries:
        apply_trust_fields(m)
        manifest_docs.append(m)
        local_docs.append(l)
        total_chunks += n
    code_anchor_count = sum(1 for m, _, _ in anchor_entries if m.get("kind") == "code_anchor")
    test_anchor_count = sum(1 for m, _, _ in anchor_entries if m.get("kind") == "test_anchor")
    code_anchor_by_repo: dict[str, int] = {}
    test_anchor_by_repo: dict[str, int] = {}
    for m, _, _ in anchor_entries:
        repo = m.get("repo", "")
        if not repo:
            continue
        if m.get("kind") == "code_anchor":
            code_anchor_by_repo[repo] = code_anchor_by_repo.get(repo, 0) + 1
        elif m.get("kind") == "test_anchor":
            test_anchor_by_repo[repo] = test_anchor_by_repo.get(repo, 0) + 1

    crosslink_stats = apply_contract_crosslinks(workspace, manifest_docs)

    structural_edges: list[dict] = []
    if index_flags.get("structural_graph"):
        repo_pairs = [(s.name, s.rel_path) for s in repo_specs]
        structural_edges = collect_structural_edges(
            workspace, repo_pairs, policy=policy
        )
        for adapter_id in index_flags.get("adapters") or []:
            if adapter_id == "null":
                structural_edges.extend(load_null_adapter_edges(workspace, repo_pairs))

    drift_findings: list[dict] = []
    if index_flags.get("drift"):
        drift_findings = detect_drift(
            workspace,
            {
                "documents": manifest_docs,
                "repos": [{"path": s.rel_path, "name": s.name} for s in repo_specs],
                "build_stats": {
                    "contract_symbols_unresolved_unique": (
                        crosslink_stats.unresolved_symbols
                        if crosslink_stats.unresolved_symbols is not None
                        else crosslink_stats.contract_symbols_unresolved_unique
                    ),
                },
            },
            openapi_enabled=bool(index_flags.get("openapi")),
            frontend_backend=True,
        )
        write_drift_suggestions(workspace, drift_findings)

    evolution_links: list[dict] = []
    if index_flags.get("git_mining"):
        evolution_links = build_evolution_links(
            workspace,
            {"documents": manifest_docs},
        )

    missing_repos = [s.rel_path for s in repo_specs if not (workspace / s.rel_path).is_dir()]
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "workspace_mapping_version": mapping_version,
        "generated_at": generated_at,
        "document_count": len(manifest_docs),
        "documents": manifest_docs,
        "build_stats": {
            "contracts_with_code_anchors": crosslink_stats.contracts_with_code_anchors,
            "anchors_with_related_doc_ids": crosslink_stats.anchors_with_related_doc_ids,
            "contract_symbols_unresolved_total": (
                crosslink_stats.contract_symbols_unresolved_total
            ),
            "contract_symbols_unresolved_unique": (
                crosslink_stats.contract_symbols_unresolved_unique
            ),
            "crosslink_source_kinds": sorted(CROSSLINK_SOURCE_KINDS),
            "structural_edge_count": len(structural_edges),
            "drift_finding_count": len(drift_findings),
            "evolution_link_count": len(evolution_links),
            "index_flags": index_flags,
            "index_policy": policy.summary(),
        },
    }
    if structural_edges:
        manifest["structural_edges"] = structural_edges
    if drift_findings:
        manifest["drift_findings"] = drift_findings
    if evolution_links:
        manifest["evolution_links"] = evolution_links
    local_index = {
        "schema_version": SCHEMA_VERSION,
        "generator": "build-search-index.sh",
        "missing_repos": missing_repos,
        "documents": local_docs,
    }

    manifest_path = generated / "search-index.manifest.json"
    local_path = generated / "search-index.local.json"
    legacy_path = generated / "search-index.json"

    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with local_path.open("w", encoding="utf-8") as f:
        json.dump(local_index, f, indent=2, ensure_ascii=False)
        f.write("\n")
    if legacy_path.exists():
        legacy_path.unlink()

    print(f"Wrote {manifest_path}")
    print(f"Wrote {local_path}")
    elapsed = time.perf_counter() - t0
    print("Summary:")
    print(f"  documents={len(manifest_docs)}")
    print(f"  code_anchors={code_anchor_count}")
    print(f"  test_anchors={test_anchor_count}")
    if code_anchor_by_repo:
        top = ", ".join(f"{k}={v}" for k, v in sorted(code_anchor_by_repo.items())[:8])
        more = " ..." if len(code_anchor_by_repo) > 8 else ""
        print(f"  code_anchors_by_repo: {top}{more}")
    if test_anchor_by_repo:
        top = ", ".join(f"{k}={v}" for k, v in sorted(test_anchor_by_repo.items())[:8])
        more = " ..." if len(test_anchor_by_repo) > 8 else ""
        print(f"  test_anchors_by_repo: {top}{more}")
    print(f"  chunks={total_chunks}")
    print(f"  contracts_with_code_anchors={crosslink_stats.contracts_with_code_anchors}")
    print(f"  anchors_with_related_doc_ids={crosslink_stats.anchors_with_related_doc_ids}")
    print(
        "  contract_symbols_unresolved_total="
        f"{crosslink_stats.contract_symbols_unresolved_total}"
    )
    print(
        "  contract_symbols_unresolved_unique="
        f"{crosslink_stats.contract_symbols_unresolved_unique}"
    )
    print(f"  missing_repos={len(missing_repos)}")
    policy_stats = policy.stats.as_dict()
    print(f"  index_mode={policy.mode}")
    print(f"  files_considered={policy_stats['files_considered']}")
    print(f"  files_allowed={policy_stats['files_allowed']}")
    print(f"  files_denied_not_included={policy_stats['files_denied_not_included']}")
    print(f"  files_denied_exclude={policy_stats['files_denied_exclude']}")
    print(f"  files_denied_ignore={policy_stats['files_denied_ignore']}")
    print(f"  dirs_pruned={policy_stats['dirs_pruned']}")
    print(f"  duration={elapsed:.1f}s")
    if missing_repos:
        print(f"[WARN] missing repos: {', '.join(missing_repos)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
