#!/usr/bin/env python3
"""Build code_anchor entries for the workspace knowledge index."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .chunk_ids import chunk_id_for
from .workspace_paths import chunk_rel_path, workspace_layout
from .index_policy import IndexPolicy, load_index_policy

CHUNK_STRATEGY = "code-anchor-v1"
ANCHOR_MAX_BYTES = 8 * 1024
# Default when contractmesh.yml omits index.code_anchor_cap_per_repo.
DEFAULT_CAP_PER_REPO = 500
# Back-compat alias for callers/tests that imported CAP_PER_REPO.
CAP_PER_REPO = DEFAULT_CAP_PER_REPO

YAML_ROOT_KEYS = frozenset(
    {"api", "auth", "jwt", "spring", "redis", "datasource", "server"}
)

# Lower rank = keep first when truncating to the per-repo cap.
ANCHOR_TYPE_PRIORITY = {
    "controller": 0,
    "service_impl": 1,
    "service": 2,
    "repository": 3,
    "client": 3,
    "filter": 4,
    "multitenancy": 5,
    "annotation": 6,
    "mapper": 6,
    "config": 7,
    "yaml_block": 8,
    "ts_service": 9,
    "ts_page": 9,
    "ts_store": 9,
    "ts_router": 9,
    # Prefer Vue SFCs over ambient TS types when a view repo hits the cap.
    "vue_component": 10,
    "go_type": 10,
    "go_func": 11,
    "python_type": 11,
    "specification": 11,
    "support": 12,
    "entity": 12,
    "java_type": 13,
    "ts_type": 14,
    "test": 40,
}

VUE_COMPONENT_GLOBS = (
    "**/src/global/components/**/*.vue",
    "**/src/system/components/**/*.vue",
    "**/src/views/*.vue",
)

JAVA_CLASS_RE = re.compile(
    r"^\s*(?:(?:public|protected|private|static|final|abstract|sealed|non-sealed)\s+)*"
    r"(?:class|interface|enum|record)\s+(\w+)",
    re.MULTILINE,
)
TS_EXPORT_CLASS_RE = re.compile(
    r"export\s+(?:default\s+)?class\s+(\w+)",
    re.MULTILINE,
)
TS_EXPORT_CONST_RE = re.compile(
    r"export\s+(?:async\s+)?(?:const|function)\s+(\w+)",
    re.MULTILINE,
)
TS_EXPORT_TYPE_RE = re.compile(
    r"export\s+(?:type|interface)\s+(\w+)",
    re.MULTILINE,
)
GO_TYPE_RE = re.compile(r"^type\s+(\w+)\s+struct", re.MULTILINE)
GO_FUNC_RE = re.compile(r"^func\s+(\w+)\s*\(", re.MULTILINE)
PYTHON_CLASS_RE = re.compile(r"^class\s+(\w+)", re.MULTILINE)
PASCAL_RE = re.compile(r"^[A-Z][a-zA-Z0-9]+$")

JAVA_PATH_HINTS = (
    "/controllers/",
    "/controller/",
    "controller.java",
    "controllerimpl.java",
    "/services/",
    "/service/",
    "service.java",
    "serviceimpl.java",
    "/repository/",
    "/repositories/",
    "/jooq/",
    "repository.java",
    "/specification/",
    "/mapper/",
    "mapper.java",
    "mapperimpl.java",
    "/config/",
    "config.java",
    "configuration.java",
    "client.java",
    "filter.java",
    "/security/",
    "/multitenancy/",
    "/util/",
    "/utils/",
    "helper.java",
    "resolver.java",
    "limiter.java",
    "guard.java",
    "/entity/",
    "/entities/",
    "/ratelimit/",
)

TS_GLOBS = (
    "**/*Service.ts",
    "**/*Page.tsx",
    "**/*Page.ts",
    "**/*Store.ts",
    "**/*Store.tsx",
    "**/api-client.ts",
    "**/api-services.ts",
    "**/http.ts",
    "**/client.ts",
    "**/requestSystem.ts",
    "**/requestAdmin.ts",
    "**/requestNoAuth.ts",
    "**/requestSystemPortal.ts",
    "**/baseService.ts",
    "**/system/types/**/*.ts",
    "**/global/types/**/*.ts",
    # Common Node/Express (and similar) backend entrypoints — kebab + PascalCase.
    "**/*Router.ts",
    "**/*-router.ts",
    "**/*Repository.ts",
    "**/*-repository.ts",
    "**/*Middleware.ts",
    "**/*-middleware.ts",
    "**/*Factory.ts",
    "**/*-factory.ts",
    "**/config.ts",
    # One-level module barrels: src/<module>/index.ts (not nested **/index.ts).
    "*/index.ts",
)


@dataclass(frozen=True)
class RepoSpec:
    name: str
    rel_path: str


def parse_repo_spec(raw: str) -> RepoSpec:
    value = raw.strip()
    if "=" in value:
        name, rel_path = value.split("=", 1)
        return RepoSpec(name=name.strip(), rel_path=rel_path.strip().strip("/"))
    rel_path = value.strip().strip("/")
    return RepoSpec(name=Path(rel_path).name, rel_path=rel_path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return f"sha256:{h.hexdigest()}"


def anchor_id_for(repo: str, rel_path: str, symbol: str) -> str:
    norm = rel_path.replace("\\", "/")
    return f"anchor:{repo}:{norm}#{symbol}"


def anchor_chunk_slug(repo: str, rel_path: str, symbol: str) -> str:
    norm = rel_path.replace("\\", "/")
    base = norm.replace("/", "-").replace(".", "-")
    sym = re.sub(r"[^a-zA-Z0-9]+", "-", symbol)
    return f"{repo}-anchor-{base}-{sym}"[:180]


def curated_anchor_keywords(
    repo: str, symbol: str, anchor_type: str, language: str
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
    add("code_anchor")
    add(symbol)
    add(anchor_type)
    add(language)
    for part in re.split(r"[^a-zA-Z0-9]+", symbol):
        add(part)
    return out[:30]


def infer_java_anchor_type(rel_path: str, class_name: str) -> str:
    norm = rel_path.replace("\\", "/").lower()
    if "controller" in class_name.lower() or "/controllers/" in norm or "/controller/" in norm:
        return "controller"
    if class_name.endswith("ServiceImpl"):
        return "service_impl"
    if class_name.endswith("Service"):
        return "service"
    if (
        class_name.endswith("Repository")
        or "/repository/" in norm
        or "/repositories/" in norm
        or "/jooq/" in norm
    ):
        return "repository"
    if class_name.endswith("Client"):
        return "client"
    if class_name.endswith(("Filter", "Guard")) or "/security/" in norm:
        return "filter"
    if class_name.endswith("Mapper") or "/mapper/" in norm:
        return "mapper"
    if "specification" in class_name.lower() or "/specification/" in norm:
        return "specification"
    if class_name.endswith(("Resolver", "Helper", "Limiter")):
        return "support"
    if class_name.endswith("Context") or "/multitenancy/" in norm:
        return "multitenancy"
    if "/config/" in norm or "config" in class_name.lower():
        return "config"
    if "/entity/" in norm or "/entities/" in norm:
        return "entity"
    return "java_type"


def should_index_java(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if parts & {"test", "tests", "target", "generated", "build"}:
        return False
    norm = str(path).replace("\\", "/").lower()
    return any(hint in norm for hint in JAVA_PATH_HINTS)


def extract_java_classes(text: str) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for m in JAVA_CLASS_RE.finditer(text):
        name = m.group(1)
        line = text[: m.start()].count("\n") + 1
        found.append((name, line))
    return found


def excerpt_from_line(text: str, start_line: int, max_bytes: int = ANCHOR_MAX_BYTES) -> tuple[str, int]:
    lines = text.splitlines()
    start_idx = max(0, start_line - 1)
    chunk_lines: list[str] = []
    size = 0
    end_line = start_line
    for i in range(start_idx, len(lines)):
        line = lines[i]
        chunk_lines.append(line)
        size += len(line.encode("utf-8")) + 1
        end_line = i + 1
        if size >= max_bytes:
            break
    return "\n".join(chunk_lines), end_line


def extract_yaml_blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^([a-zA-Z][\w-]*):\s*$", lines[i])
        if m and m.group(1).lower() in YAML_ROOT_KEYS:
            key = m.group(1)
            block_lines = [lines[i]]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if nxt and not nxt[0].isspace():
                    if re.match(r"^[a-zA-Z][\w-]*:\s*$", nxt):
                        break
                block_lines.append(nxt)
                i += 1
            blocks.append((key, "\n".join(block_lines)))
            continue
        i += 1
    return blocks


def write_anchor(
    workspace: Path,
    chunks_root: Path,
    repo: str,
    rel_path: str,
    symbol: str,
    title: str,
    chunk_text: str,
    anchor_type: str,
    language: str,
    line_start: int | None,
    line_end: int | None,
    roles: dict[str, str],
    weight: int,
    kind: str = "code_anchor",
) -> tuple[dict, dict, int]:
    doc_id = anchor_id_for(repo, rel_path, symbol)
    keywords = curated_anchor_keywords(repo, symbol, anchor_type, language)
    slug = anchor_chunk_slug(repo, rel_path, symbol)
    chunk_dir = chunks_root / repo
    chunk_dir.mkdir(parents=True, exist_ok=True)
    layout = workspace_layout(workspace)
    chunk_rel = chunk_rel_path(layout, repo, slug)
    chunk_abs = workspace / chunk_rel

    row = {
        "chunk_id": chunk_id_for(doc_id, 0),
        "doc_id": doc_id,
        "title": title,
        "heading": symbol,
        "text": chunk_text.strip(),
    }
    with chunk_abs.open("w", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    abs_path = workspace / rel_path
    manifest: dict = {
        "id": doc_id,
        "repo": repo,
        "path": rel_path.replace("\\", "/"),
        "kind": kind,
        "symbol": symbol,
        "anchor_type": anchor_type,
        "language": language,
        "title": title,
        "headings": [symbol],
        "keywords": keywords,
        "known_gap_ids": [],
        "links": {"related": []},
        "weight": weight,
        "chunking": {"strategy": CHUNK_STRATEGY},
        "embedding": {"status": "pending", "model": None, "dimensions": None},
    }
    if line_start is not None:
        manifest["line_start"] = line_start
    if line_end is not None:
        manifest["line_end"] = line_end
    role = roles.get(repo)
    if role:
        manifest["role"] = role

    local = {
        "id": doc_id,
        "content_hash": sha256_file(abs_path) if abs_path.is_file() else "",
        "absolute_path": str(abs_path.resolve()) if abs_path.is_file() else "",
        "chunk_count": 1,
        "chunk_path": chunk_rel.replace("\\", "/"),
    }
    return manifest, local, 1


def index_java_file(
    workspace: Path,
    abs_path: Path,
    rel_path: str,
    repo: str,
    chunks_root: Path,
    roles: dict[str, str],
    weight: int,
) -> list[tuple[dict, dict, int]]:
    if not should_index_java(abs_path):
        return []
    text = abs_path.read_text(encoding="utf-8", errors="replace")
    out: list[tuple[dict, dict, int]] = []
    for class_name, line_no in extract_java_classes(text):
        excerpt, end_line = excerpt_from_line(text, line_no)
        atype = infer_java_anchor_type(rel_path, class_name)
        title = f"{class_name} ({repo})"
        out.append(
            write_anchor(
                workspace,
                chunks_root,
                repo,
                rel_path,
                class_name,
                title,
                excerpt,
                atype,
                "java",
                line_no,
                end_line,
                roles,
                weight,
            )
        )
    return out


def index_yaml_file(
    workspace: Path,
    abs_path: Path,
    rel_path: str,
    repo: str,
    chunks_root: Path,
    roles: dict[str, str],
    weight: int,
) -> list[tuple[dict, dict, int]]:
    text = abs_path.read_text(encoding="utf-8", errors="replace")
    blocks = extract_yaml_blocks(text)
    out: list[tuple[dict, dict, int]] = []
    if blocks:
        for key, body in blocks:
            symbol = f"application-{key}"
            title = f"{Path(rel_path).name} — {key}"
            out.append(
                write_anchor(
                    workspace,
                    chunks_root,
                    repo,
                    rel_path,
                    symbol,
                    title,
                    body,
                    "yaml_block",
                    "yaml",
                    None,
                    None,
                    roles,
                    weight,
                )
            )
    else:
        fallback = text[:ANCHOR_MAX_BYTES]
        symbol = Path(rel_path).stem
        out.append(
            write_anchor(
                workspace,
                chunks_root,
                repo,
                rel_path,
                symbol,
                f"{symbol} ({repo})",
                fallback,
                "config",
                "yaml",
                1,
                min(len(text.splitlines()), 80),
                roles,
                weight,
            )
        )
    return out


def _typescript_stem_fallback(stem: str) -> list[str]:
    if stem.endswith(("Service", "Page", "Store")) or stem.startswith("request"):
        return [stem]
    if stem in {"api-client", "api-services", "http", "client", "config"}:
        return [stem.replace("-", "_")]
    for suffix in (
        "-router",
        "-repository",
        "-middleware",
        "-factory",
        "Router",
        "Repository",
        "Middleware",
        "Factory",
    ):
        if stem.endswith(suffix):
            return [stem.replace("-", "_")]
    if stem == "index":
        return ["index"]
    return []


def _infer_ts_anchor_type(
    rel_path: str, symbol: str, *, is_type_file: bool, type_symbols: set[str]
) -> str:
    if is_type_file or symbol in type_symbols:
        return "ts_type"
    if symbol.endswith("Page"):
        return "ts_page"
    if symbol.endswith("Store"):
        return "ts_store"
    norm = rel_path.replace("\\", "/").lower()
    stem = Path(rel_path).stem.lower()
    if (
        "router" in symbol.lower()
        or stem.endswith("router")
        or stem.endswith("-router")
        or "/routes/" in norm
        or "/routers/" in norm
    ):
        return "ts_router"
    return "ts_service"


def index_typescript_file(
    workspace: Path,
    abs_path: Path,
    rel_path: str,
    repo: str,
    chunks_root: Path,
    roles: dict[str, str],
    weight: int,
) -> list[tuple[dict, dict, int]]:
    text = abs_path.read_text(encoding="utf-8", errors="replace")
    type_symbols = {m.group(1) for m in TS_EXPORT_TYPE_RE.finditer(text)}
    symbols: list[str] = []
    for pat in (TS_EXPORT_CLASS_RE, TS_EXPORT_CONST_RE, TS_EXPORT_TYPE_RE):
        symbols.extend(m.group(1) for m in pat.finditer(text))
    if not symbols:
        symbols = _typescript_stem_fallback(abs_path.stem)
    if not symbols:
        return []

    is_type_file = "/types/" in rel_path.replace("\\", "/")
    line_no = 1
    excerpt = text[:ANCHOR_MAX_BYTES]
    out: list[tuple[dict, dict, int]] = []
    for sym in sorted(set(symbols)):
        atype = _infer_ts_anchor_type(
            rel_path, sym, is_type_file=is_type_file, type_symbols=type_symbols
        )
        out.append(
            write_anchor(
                workspace,
                chunks_root,
                repo,
                rel_path,
                sym,
                f"{sym} ({repo})",
                excerpt,
                atype,
                "typescript",
                line_no,
                min(len(text.splitlines()), 120),
                roles,
                weight,
            )
        )
    return out


def index_go_file(
    workspace: Path,
    abs_path: Path,
    rel_path: str,
    repo: str,
    chunks_root: Path,
    roles: dict[str, str],
    weight: int,
) -> list[tuple[dict, dict, int]]:
    text = abs_path.read_text(encoding="utf-8", errors="replace")
    out: list[tuple[dict, dict, int]] = []
    for m in GO_TYPE_RE.finditer(text):
        name = m.group(1)
        line = text[: m.start()].count("\n") + 1
        excerpt, end_line = excerpt_from_line(text, line)
        out.append(
            write_anchor(
                workspace,
                chunks_root,
                repo,
                rel_path,
                name,
                f"{name} ({repo})",
                excerpt,
                "go_type",
                "go",
                line,
                end_line,
                roles,
                weight,
            )
        )
    for m in GO_FUNC_RE.finditer(text):
        name = m.group(1)
        if not name[0].isupper():
            continue
        line = text[: m.start()].count("\n") + 1
        excerpt, end_line = excerpt_from_line(text, line)
        out.append(
            write_anchor(
                workspace,
                chunks_root,
                repo,
                rel_path,
                name,
                f"{name} ({repo})",
                excerpt,
                "go_func",
                "go",
                line,
                end_line,
                roles,
                weight,
            )
        )
    return out


def collect_java_sources(
    workspace: Path,
    repo_path: str,
    policy: IndexPolicy | None = None,
) -> list[Path]:
    base = workspace / repo_path
    roots = [base / "src" / "main" / "java", base / "src" / "main" / "kotlin"]
    files: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if policy is not None:
                policy.prune_walk_dirs(Path(dirpath), dirnames)
            for name in filenames:
                if name.endswith((".java", ".kt")):
                    files.append(Path(dirpath) / name)
    return sorted(files)


def collect_java_tests(
    workspace: Path,
    repo_path: str,
    policy: IndexPolicy | None = None,
) -> list[Path]:
    base = workspace / repo_path / "src" / "test" / "java"
    files: list[Path] = []
    if not base.is_dir():
        return files
    for dirpath, dirnames, filenames in os.walk(base):
        if policy is not None:
            policy.prune_walk_dirs(Path(dirpath), dirnames)
        for name in filenames:
            if name.endswith((".java", ".kt")):
                files.append(Path(dirpath) / name)
    return sorted(files)


def collect_ts_sources(workspace: Path, repo_path: str) -> list[Path]:
    """Collect curated TypeScript sources under ``src`` and nested ``*/src``.

    Layouts such as ``server/src`` or ``frontend/src`` are included when the
    repo root is ``.``. Only files matching ``TS_GLOBS`` become anchors.
    """
    base = workspace / repo_path
    if not base.is_dir():
        return []
    src_roots: list[Path] = []
    direct = base / "src"
    if direct.is_dir():
        src_roots.append(direct)
    skip = {
        "node_modules",
        "dist",
        "build",
        "coverage",
        ".git",
        ".contractmesh",
        "venv",
        ".venv",
        "target",
        "tests",
        "test",
        "__tests__",
        "vendor",
        "third_party",
        "third-party",
        "fixtures",
        "examples",
        "example",
        "tmp",
        "temp",
        "out",
    }
    try:
        children = list(base.iterdir())
    except OSError:
        children = []
    for child in children:
        if not child.is_dir() or child.name in skip or child.name.startswith("."):
            continue
        nested = child / "src"
        if nested.is_dir():
            src_roots.append(nested)

    found: set[Path] = set()
    for src_root in src_roots:
        for pattern in TS_GLOBS:
            for p in src_root.glob(pattern):
                if not p.is_file() or "node_modules" in p.parts:
                    continue
                name = p.name
                if name.endswith((".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx")):
                    continue
                found.add(p)
    return sorted(found)


def collect_ts_tests(workspace: Path, repo_path: str) -> list[Path]:
    base = workspace / repo_path
    found: set[Path] = set()
    if not base.is_dir():
        return []
    patterns = (
        "src/**/*.test.ts",
        "src/**/*.spec.ts",
        "*/src/**/*.test.ts",
        "*/src/**/*.spec.ts",
        "test/**/*.ts",
        "tests/**/*.ts",
        "__tests__/**/*.ts",
    )
    for pattern in patterns:
        for p in base.glob(pattern):
            if p.is_file() and "node_modules" not in p.parts:
                found.add(p)
    return sorted(found)


def collect_go_sources(
    workspace: Path,
    repo_path: str,
    policy: IndexPolicy | None = None,
) -> list[Path]:
    base = workspace / repo_path
    found: list[Path] = []
    for sub in ("internal", "cmd"):
        root = base / sub
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if policy is not None:
                policy.prune_walk_dirs(Path(dirpath), dirnames)
            if "sdk" in Path(dirpath).parts:
                continue
            for name in filenames:
                if name.endswith(".go") and not name.endswith("_test.go"):
                    found.append(Path(dirpath) / name)
    return sorted(found)


def collect_go_tests(
    workspace: Path,
    repo_path: str,
    policy: IndexPolicy | None = None,
) -> list[Path]:
    base = workspace / repo_path
    found: list[Path] = []
    for sub in ("internal", "cmd"):
        root = base / sub
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if policy is not None:
                policy.prune_walk_dirs(Path(dirpath), dirnames)
            for name in filenames:
                if name.endswith("_test.go"):
                    found.append(Path(dirpath) / name)
    return sorted(found)


def collect_python_sources(workspace: Path, repo_path: str) -> list[Path]:
    base = workspace / repo_path
    found: set[Path] = set()
    if not base.is_dir():
        return []
    for pattern in ("src/**/*.py", "*.py"):
        for p in base.glob(pattern):
            if not p.is_file():
                continue
            try:
                rel_parts = p.relative_to(base).parts
            except ValueError:
                continue
            if rel_parts and rel_parts[0].lower() in {"tests", "test", "__pycache__", ".venv", "venv"}:
                continue
            if p.name.startswith("test_"):
                continue
            found.add(p)
    return sorted(found)


def collect_python_tests(workspace: Path, repo_path: str) -> list[Path]:
    base = workspace / repo_path
    found: set[Path] = set()
    if not base.is_dir():
        return []
    for pattern in ("tests/**/*.py", "test/**/*.py", "test_*.py"):
        for p in base.glob(pattern):
            if not p.is_file():
                continue
            if "__pycache__" in p.parts:
                continue
            found.add(p)
    return sorted(found)


def index_python_file(
    workspace: Path,
    abs_path: Path,
    rel_path: str,
    repo: str,
    chunks_root: Path,
    roles: dict[str, str],
    weight: int,
) -> list[tuple[dict, dict, int]]:
    text = abs_path.read_text(encoding="utf-8", errors="replace")
    out: list[tuple[dict, dict, int]] = []
    for m in PYTHON_CLASS_RE.finditer(text):
        name = m.group(1)
        if name.startswith("_"):
            continue
        line = text[: m.start()].count("\n") + 1
        excerpt, end_line = excerpt_from_line(text, line)
        out.append(
            write_anchor(
                workspace,
                chunks_root,
                repo,
                rel_path,
                name,
                f"{name} ({repo})",
                excerpt,
                "service" if name.endswith("Service") else "python_type",
                "python",
                line,
                end_line,
                roles,
                weight,
            )
        )
    return out


def index_test_file(
    workspace: Path,
    abs_path: Path,
    rel_path: str,
    repo: str,
    chunks_root: Path,
    roles: dict[str, str],
    weight: int,
) -> list[tuple[dict, dict, int]]:
    text = abs_path.read_text(encoding="utf-8", errors="replace")
    symbols: list[str] = []
    suffix = abs_path.suffix.lower()
    if suffix in (".java", ".kt"):
        symbols = [name for name, _ in extract_java_classes(text)]
    elif suffix == ".ts":
        for pat in (TS_EXPORT_CLASS_RE, TS_EXPORT_CONST_RE):
            symbols.extend(m.group(1) for m in pat.finditer(text))
    elif suffix == ".go":
        symbols.extend(m.group(1) for m in GO_FUNC_RE.finditer(text))
    elif suffix == ".py":
        symbols = [name for name in PYTHON_CLASS_RE.findall(text) if not name.startswith("_")]
    if not symbols:
        symbols = [abs_path.stem]

    out: list[tuple[dict, dict, int]] = []
    for sym in sorted(set(symbols)):
        out.append(
            write_anchor(
                workspace,
                chunks_root,
                repo,
                rel_path,
                sym,
                f"{sym} ({repo})",
                text[:ANCHOR_MAX_BYTES],
                "test",
                suffix.lstrip(".") or "test",
                1,
                min(len(text.splitlines()), 160),
                roles,
                weight,
                kind="test_anchor",
            )
        )
    return out


def collect_yaml_configs(workspace: Path, repo_path: str) -> list[Path]:
    res = workspace / repo_path / "src" / "main" / "resources"
    out: list[Path] = []
    for name in ("application.yml", "application.yaml"):
        p = res / name
        if p.is_file():
            out.append(p)
    return out


def index_vue_file(
    workspace: Path,
    abs_path: Path,
    rel_path: str,
    repo: str,
    chunks_root: Path,
    roles: dict[str, str],
    weight: int,
) -> list[tuple[dict, dict, int]]:
    symbol = abs_path.stem
    if not PASCAL_RE.match(symbol):
        return []
    text = abs_path.read_text(encoding="utf-8", errors="replace")
    excerpt = text[:ANCHOR_MAX_BYTES]
    return [
        write_anchor(
            workspace,
            chunks_root,
            repo,
            rel_path,
            symbol,
            f"{symbol} ({repo})",
            excerpt,
            "vue_component",
            "vue",
            1,
            min(len(text.splitlines()), 120),
            roles,
            weight,
        )
    ]


def collect_vue_sources(workspace: Path, repo_path: str) -> list[Path]:
    """Curated Vue SFCs: top-level views + system/global components."""
    base = workspace / repo_path
    if not base.is_dir():
        return []
    found: set[Path] = set()
    for pattern in VUE_COMPONENT_GLOBS:
        for p in base.glob(pattern):
            if p.is_file() and "node_modules" not in p.parts:
                found.add(p)
    return sorted(found)


def resolve_cap_per_repo(raw: object | None) -> int:
    """Parse index.code_anchor_cap_per_repo (YAML subset may yield str)."""
    if raw is None or raw is False or raw == "":
        return DEFAULT_CAP_PER_REPO
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_CAP_PER_REPO
    return max(1, value)


def normalize_cap_by_repo(raw: object | None) -> dict[str, int]:
    """Parse index.code_anchor_cap_by_repo.

    Supported forms (community-friendly):
    - mapping: ``{ "billing-api": 1200 }``
    - list of ``repo=N`` strings (works with the contractmesh.yml subset parser)::

        code_anchor_cap_by_repo:
          - billing-api=1200
    """
    out: dict[str, int] = {}
    if raw is None or raw is False or raw == "":
        return out
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, list):
        items = []
        for item in raw:
            text = str(item).strip().strip("\"'")
            if "=" not in text:
                continue
            name, value = text.split("=", 1)
            items.append((name.strip(), value.strip()))
    else:
        return out
    for name, value in items:
        key = str(name).strip()
        if not key:
            continue
        try:
            out[key] = max(1, int(str(value).strip()))
        except (TypeError, ValueError):
            continue
    return out


def resolve_repo_cap(
    repo: str,
    *,
    default_cap: int,
    cap_by_repo: dict[str, int] | None = None,
) -> int:
    """Return the per-repo anchor cap, preferring explicit overrides."""
    if cap_by_repo and repo in cap_by_repo:
        return max(1, int(cap_by_repo[repo]))
    return max(1, int(default_cap))


def anchor_sort_key(entry: tuple[dict, dict, int]) -> tuple[int, int, str]:
    """Prefer high-signal anchor types, then higher doc weight, then path."""
    manifest = entry[0]
    atype = str(manifest.get("anchor_type") or "")
    type_rank = ANCHOR_TYPE_PRIORITY.get(atype, 50)
    # Negate so higher document weight sorts earlier (stable with type rank).
    doc_weight = -int(manifest.get("weight") or 0)
    return (type_rank, doc_weight, str(manifest.get("path") or ""))


def collect_code_anchors(
    workspace: Path,
    repos: list[str],
    chunks_root: Path,
    roles: dict[str, str],
    *,
    weight: int = 58,
    policy: IndexPolicy | None = None,
    cap_per_repo: int | None = None,
    cap_by_repo: dict[str, int] | object | None = None,
) -> tuple[list[tuple[dict, dict, int]], dict[str, int], dict[str, dict[str, int]]]:
    """Return (entries, per_repo_counts, truncation_by_repo)."""
    all_entries: list[tuple[dict, dict, int]] = []
    per_repo: dict[str, int] = {}
    truncation_by_repo: dict[str, dict[str, int]] = {}
    policy = policy or load_index_policy(workspace)
    default_cap = (
        DEFAULT_CAP_PER_REPO
        if cap_per_repo is None
        else resolve_cap_per_repo(cap_per_repo)
    )
    overrides = normalize_cap_by_repo(cap_by_repo)

    def visible(paths: list[Path]) -> list[Path]:
        return [p for p in paths if not policy.ignores(p)]

    for raw_repo in repos:
        spec = parse_repo_spec(raw_repo)
        repo = spec.name
        repo_path = spec.rel_path
        if not (workspace / repo_path).is_dir():
            continue
        cap = resolve_repo_cap(repo, default_cap=default_cap, cap_by_repo=overrides)
        repo_entries: list[tuple[dict, dict, int]] = []

        for abs_path in visible(collect_java_sources(workspace, repo_path, policy)):
            rel = abs_path.relative_to(workspace).as_posix()
            repo_entries.extend(
                index_java_file(
                    workspace, abs_path, rel, repo, chunks_root, roles, weight
                )
            )

        for abs_path in visible(collect_yaml_configs(workspace, repo_path)):
            rel = abs_path.relative_to(workspace).as_posix()
            repo_entries.extend(
                index_yaml_file(
                    workspace, abs_path, rel, repo, chunks_root, roles, weight
                )
            )

        for abs_path in visible(collect_ts_sources(workspace, repo_path)):
            rel = abs_path.relative_to(workspace).as_posix()
            repo_entries.extend(
                index_typescript_file(
                    workspace, abs_path, rel, repo, chunks_root, roles, weight
                )
            )

        for abs_path in visible(collect_vue_sources(workspace, repo_path)):
            rel = abs_path.relative_to(workspace).as_posix()
            repo_entries.extend(
                index_vue_file(
                    workspace, abs_path, rel, repo, chunks_root, roles, weight
                )
            )

        for abs_path in visible(collect_go_sources(workspace, repo_path, policy)):
            rel = abs_path.relative_to(workspace).as_posix()
            repo_entries.extend(
                index_go_file(
                    workspace, abs_path, rel, repo, chunks_root, roles, weight
                )
            )

        for abs_path in visible(collect_python_sources(workspace, repo_path)):
            rel = abs_path.relative_to(workspace).as_posix()
            repo_entries.extend(
                index_python_file(
                    workspace, abs_path, rel, repo, chunks_root, roles, weight
                )
            )

        test_paths = (
            collect_java_tests(workspace, repo_path, policy)
            + collect_ts_tests(workspace, repo_path)
            + collect_go_tests(workspace, repo_path, policy)
            + collect_python_tests(workspace, repo_path)
        )
        for abs_path in visible(test_paths):
            rel = abs_path.relative_to(workspace).as_posix()
            repo_entries.extend(
                index_test_file(
                    workspace, abs_path, rel, repo, chunks_root, roles, weight
                )
            )

        if len(repo_entries) > cap:
            repo_entries.sort(key=anchor_sort_key)
            total = len(repo_entries)
            dropped = total - cap
            truncation_by_repo[repo] = {
                "total": total,
                "kept": cap,
                "dropped": dropped,
            }
            print(
                f"[WARN] code_anchor truncated for {repo}: "
                f"dropped {dropped}, kept {cap}/{total} "
                f"(by anchor_type priority + weight)",
            )
            repo_entries = repo_entries[:cap]

        per_repo[repo] = len(repo_entries)
        all_entries.extend(repo_entries)

    return all_entries, per_repo, truncation_by_repo
