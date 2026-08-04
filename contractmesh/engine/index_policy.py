#!/usr/bin/env python3
"""Index security policy: allowlist/denylist + ignore layers.

Evaluation order (workspace-relative paths):

  repos + docs roots (caller scope)
  → include globs (allowlist mode only)
  → exclude globs (manifest, both modes)
  → .contractmeshignore
  → DEFAULT_IGNORE_PATTERNS

Repo-scoped patterns use ``repo_name:glob`` (glob is relative to that repo path).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal

from .contractmesh_ignore import ContractMeshIgnore, load_contractmesh_ignore

IndexMode = Literal["denylist", "allowlist"]

_REPO_SCOPED_RE = re.compile(r"^([A-Za-z0-9._-]+):(.+)$")


@dataclass
class IndexPolicyStats:
    """Mutable counters for one index build or explain session."""

    considered: int = 0
    allowed: int = 0
    denied_not_included: int = 0
    denied_exclude: int = 0
    denied_ignore: int = 0
    dirs_pruned: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "files_considered": self.considered,
            "files_allowed": self.allowed,
            "files_denied_not_included": self.denied_not_included,
            "files_denied_exclude": self.denied_exclude,
            "files_denied_ignore": self.denied_ignore,
            "dirs_pruned": self.dirs_pruned,
        }


@dataclass(frozen=True)
class PathDecision:
    """Result of evaluating one path against the index policy."""

    path: str
    allowed: bool
    reason: str
    mode: IndexMode
    matched_include: str | None = None
    matched_exclude: str | None = None
    matched_ignore: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "allowed": self.allowed,
            "reason": self.reason,
            "mode": self.mode,
            "matched_include": self.matched_include,
            "matched_exclude": self.matched_exclude,
            "matched_ignore": self.matched_ignore,
        }


@dataclass
class CompiledPattern:
    """One include/exclude pattern with optional repo scope."""

    raw: str
    glob: str
    regex: re.Pattern[str] = field(repr=False, compare=False)
    repo: str | None = None


def _strip_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Convert a gitignore-inspired glob to a regex (full match on relative path)."""
    pat = pattern.replace("\\", "/").strip()
    anchored = pat.startswith("/")
    if anchored:
        pat = pat[1:]
    dir_only = pat.endswith("/")
    if dir_only:
        pat = pat.rstrip("/")

    parts: list[str] = []
    i = 0
    while i < len(pat):
        if pat.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
            continue
        if pat[i : i + 2] == "**":
            parts.append(".*")
            i += 2
            continue
        ch = pat[i]
        if ch == "*":
            parts.append("[^/]*")
        elif ch == "?":
            parts.append("[^/]")
        elif ch == "[":
            j = i + 1
            if j < len(pat) and pat[j] in ("!", "]"):
                j += 1
            while j < len(pat) and pat[j] != "]":
                j += 1
            if j >= len(pat):
                parts.append(re.escape(ch))
            else:
                parts.append(pat[i : j + 1])
                i = j
        else:
            parts.append(re.escape(ch))
        i += 1

    body = "".join(parts)
    if not anchored and "/" not in pat.replace("**/", "").replace("**", ""):
        # Basename-style pattern: match any path segment or full relative path.
        regex = rf"(?:^{body}$|(?:^.*/{body}$))"
    else:
        regex = rf"^{body}$"
    if dir_only:
        # Directory patterns also match everything under the directory.
        regex = rf"(?:{regex})|(?:^{body}/.*$)"
    return re.compile(regex)


def compile_pattern(raw: str, *, repo_names: Iterable[str] | None = None) -> CompiledPattern:
    text = _strip_quotes(raw)
    if not text or text.startswith("#"):
        raise ValueError(f"empty index pattern: {raw!r}")
    repo: str | None = None
    glob = text
    known = set(repo_names or ())
    match = _REPO_SCOPED_RE.match(text)
    if match and match.group(1) in known:
        repo = match.group(1)
        glob = _strip_quotes(match.group(2)).lstrip("/")
        if not glob:
            raise ValueError(f"empty repo-scoped glob: {raw!r}")
    return CompiledPattern(raw=text, glob=glob, regex=_glob_to_regex(glob), repo=repo)


def _pattern_matches(
    compiled: CompiledPattern,
    rel: str,
    *,
    repo_name: str | None,
    repo_path: str | None,
) -> bool:
    if compiled.repo is not None:
        if repo_name != compiled.repo:
            return False
        if not repo_path or repo_path in (".", ""):
            candidate = rel
        else:
            prefix = repo_path.rstrip("/") + "/"
            if rel == repo_path.rstrip("/"):
                candidate = ""
            elif rel.startswith(prefix):
                candidate = rel[len(prefix) :]
            else:
                return False
        if candidate == "":
            return False
        return bool(compiled.regex.match(candidate))
    return bool(compiled.regex.match(rel))


def _include_can_match_under(
    compiled: CompiledPattern,
    dir_rel: str,
    *,
    repo_name: str | None,
    repo_path: str | None,
) -> bool:
    """Return True if some path under dir_rel could match this include."""
    dir_norm = dir_rel.strip("/")
    # Probe a synthetic child path that is likely to match broad patterns.
    probe = f"{dir_norm}/__contractmesh_probe__" if dir_norm else "__contractmesh_probe__"
    if _pattern_matches(compiled, probe, repo_name=repo_name, repo_path=repo_path):
        return True
    if _pattern_matches(compiled, dir_norm, repo_name=repo_name, repo_path=repo_path):
        return True

    # Prefix / segment checks for patterns like src/** or docs/contracts/**
    glob = compiled.glob.replace("\\", "/").strip("/")
    if compiled.repo is not None:
        if repo_name != compiled.repo:
            return False
        if repo_path and repo_path not in (".", ""):
            repo_prefix = repo_path.rstrip("/")
            if dir_norm == repo_prefix or dir_norm.startswith(repo_prefix + "/"):
                local = "" if dir_norm == repo_prefix else dir_norm[len(repo_prefix) + 1 :]
            elif repo_prefix.startswith(dir_norm + "/") or not dir_norm:
                return True
            else:
                return False
        else:
            local = dir_norm
        return _glob_prefix_compatible(glob, local)

    return _glob_prefix_compatible(glob, dir_norm)


def _glob_prefix_compatible(glob: str, dir_rel: str) -> bool:
    if not dir_rel:
        return True
    if "**" in glob:
        # Conservative: keep walking unless the fixed prefix clearly diverges.
        head = glob.split("**", 1)[0].strip("/")
        if not head:
            return True
        head_parts = head.split("/")
        dir_parts = dir_rel.split("/")
        for hp, dp in zip(head_parts, dir_parts):
            if hp in ("*", "?"):
                continue
            if any(ch in hp for ch in "*?[]"):
                continue
            if hp != dp:
                return False
        return True
    # Fixed-path prefix: docs/contracts/** vs docs / docs/contracts / src
    glob_parts = [p for p in glob.replace("**/", "").split("/") if p and p != "**"]
    dir_parts = dir_rel.split("/")
    for gp, dp in zip(glob_parts, dir_parts):
        if any(ch in gp for ch in "*?[]"):
            # soft match for that segment
            if not re.fullmatch(_segment_glob_to_regex(gp), dp):
                return False
            continue
        if gp != dp:
            return False
    return True


def _segment_glob_to_regex(segment: str) -> str:
    out: list[str] = []
    for ch in segment:
        if ch == "*":
            out.append(".*")
        elif ch == "?":
            out.append(".")
        else:
            out.append(re.escape(ch))
    return "".join(out)


@dataclass
class IndexPolicy:
    """Unified index boundary for every file discovery path."""

    workspace: Path
    mode: IndexMode
    include: tuple[CompiledPattern, ...]
    exclude: tuple[CompiledPattern, ...]
    ignore: ContractMeshIgnore
    repo_paths: dict[str, str] = field(default_factory=dict)
    stats: IndexPolicyStats = field(default_factory=IndexPolicyStats)

    def resolve_repo(self, rel: str) -> tuple[str | None, str | None]:
        """Best-effort (repo_name, repo_path) for a workspace-relative path."""
        rel_n = rel.strip("/")
        best_name: str | None = None
        best_path: str | None = None
        best_len = -1
        for name, path in self.repo_paths.items():
            if path in (".", ""):
                # Workspace-root repo matches everything; keep looking for a
                # more specific repo prefix first.
                if best_len < 0:
                    best_name, best_path, best_len = name, path, 0
                continue
            prefix = path.rstrip("/")
            if rel_n == prefix or rel_n.startswith(prefix + "/"):
                if len(prefix) > best_len:
                    best_name, best_path, best_len = name, path, len(prefix)
        return best_name, best_path

    def first_matching(
        self,
        patterns: Iterable[CompiledPattern],
        rel: str,
        *,
        repo_name: str | None = None,
        repo_path: str | None = None,
    ) -> CompiledPattern | None:
        if repo_name is None and repo_path is None:
            repo_name, repo_path = self.resolve_repo(rel)
        for pattern in patterns:
            if _pattern_matches(pattern, rel, repo_name=repo_name, repo_path=repo_path):
                return pattern
        return None

    def explain(self, path: Path | str) -> PathDecision:
        rel = self._normalize(path)
        repo_name, repo_path = self.resolve_repo(rel)
        matched_include: str | None = None
        if self.mode == "allowlist":
            include_hit = self.first_matching(
                self.include, rel, repo_name=repo_name, repo_path=repo_path
            )
            if include_hit is None:
                return PathDecision(
                    path=rel,
                    allowed=False,
                    reason="not_included",
                    mode=self.mode,
                )
            matched_include = include_hit.raw

        exclude_hit = self.first_matching(
            self.exclude, rel, repo_name=repo_name, repo_path=repo_path
        )
        if exclude_hit is not None:
            return PathDecision(
                path=rel,
                allowed=False,
                reason="excluded",
                mode=self.mode,
                matched_include=matched_include,
                matched_exclude=exclude_hit.raw,
            )

        # Reuse ContractMeshIgnore matcher; find which pattern hit for explain.
        if self.ignore.ignores(rel):
            matched_ignore = self._matching_ignore_pattern(rel)
            return PathDecision(
                path=rel,
                allowed=False,
                reason="ignored",
                mode=self.mode,
                matched_include=matched_include,
                matched_ignore=matched_ignore,
            )

        return PathDecision(
            path=rel,
            allowed=True,
            reason="allowed",
            mode=self.mode,
            matched_include=matched_include,
        )

    def allows(self, path: Path | str, *, count: bool = True) -> bool:
        decision = self.explain(path)
        if count:
            self.stats.considered += 1
            if decision.allowed:
                self.stats.allowed += 1
            elif decision.reason == "not_included":
                self.stats.denied_not_included += 1
            elif decision.reason == "excluded":
                self.stats.denied_exclude += 1
            else:
                self.stats.denied_ignore += 1
        return decision.allowed

    def ignores(self, path: Path | str, *, count: bool = True) -> bool:
        """Compatibility alias: True when the path must not be indexed."""
        return not self.allows(path, count=count)

    def may_enter(self, dir_path: Path | str, *, count: bool = True) -> bool:
        """Whether a directory walk should descend into dir_path."""
        rel = self._normalize(dir_path)
        if not rel:
            return True
        repo_name, repo_path = self.resolve_repo(rel)

        # Directory excluded/ignored → prune.
        exclude_hit = self.first_matching(
            self.exclude, rel, repo_name=repo_name, repo_path=repo_path
        )
        if exclude_hit is not None or self.ignore.ignores(rel):
            if count:
                self.stats.dirs_pruned += 1
            return False
        # Also prune if any path segment matches directory ignore patterns via child probe.
        if self.ignore.ignores(f"{rel}/") or self.ignore.ignores(rel + "/.keep"):
            # Conservative: only prune when the directory itself is ignored.
            pass

        if self.mode == "denylist":
            return True

        for include in self.include:
            if _include_can_match_under(
                include, rel, repo_name=repo_name, repo_path=repo_path
            ):
                return True
        if count:
            self.stats.dirs_pruned += 1
        return False

    def prune_walk_dirs(self, root: Path, dirnames: list[str]) -> None:
        """In-place filter for ``os.walk`` dirnames."""
        kept: list[str] = []
        for name in dirnames:
            child = root / name
            if self.may_enter(child):
                kept.append(name)
        dirnames[:] = kept

    def _matching_ignore_pattern(self, rel: str) -> str | None:
        parts = rel.split("/")
        for pattern in self.ignore.patterns:
            if self.ignore._matches(pattern, rel, parts):  # noqa: SLF001 — explain helper
                return pattern
        return None

    def _normalize(self, path: Path | str) -> str:
        raw = Path(path)
        if raw.is_absolute():
            try:
                raw = raw.resolve().relative_to(self.workspace)
            except ValueError:
                # macOS often yields /var/... from os.walk while resolve() is
                # /private/var/... — retry after resolving both sides.
                try:
                    raw = Path(path).resolve().relative_to(self.workspace.resolve())
                except ValueError:
                    pass
        return raw.as_posix().strip("/")

    def summary(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "include": [p.raw for p in self.include],
            "exclude": [p.raw for p in self.exclude],
            "repo_scoped_include": [p.raw for p in self.include if p.repo],
            "repo_scoped_exclude": [p.raw for p in self.exclude if p.repo],
            "stats": self.stats.as_dict(),
        }


def normalize_index_security(index: dict[str, Any]) -> dict[str, Any]:
    """Normalize include/exclude; do not invent index.mode."""
    out = dict(index)
    if "mode" in out:
        mode_raw = out.get("mode")
        if mode_raw is None or str(mode_raw).strip() == "":
            out.pop("mode", None)
        else:
            out["mode"] = str(mode_raw).strip().lower()
    else:
        out.pop("mode", None)

    def _as_patterns(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            text = _strip_quotes(value)
            return [text] if text else []
        if isinstance(value, list):
            patterns: list[str] = []
            for item in value:
                text = _strip_quotes(str(item))
                if text and not text.startswith("#"):
                    patterns.append(text)
            return patterns
        return []

    out["include"] = _as_patterns(out.get("include"))
    out["exclude"] = _as_patterns(out.get("exclude"))
    return out


def validate_index_security(
    index: dict[str, Any],
    *,
    repo_names: Iterable[str] | None = None,
    source: str = "contractmesh.yml",
) -> list[str]:
    """Return validation errors for index security settings."""
    errors: list[str] = []
    mode_raw = index.get("mode")
    if mode_raw is None or str(mode_raw).strip() == "":
        errors.append(
            f"{source}: index.mode is required ('allowlist' or 'denylist'). "
            "A workspace without an explicit index.mode is invalid."
        )
        return errors
    mode = str(mode_raw).strip().lower()
    if mode not in ("denylist", "allowlist"):
        errors.append(
            f"{source}: index.mode must be 'allowlist' or 'denylist' (got {mode!r})"
        )
        return errors

    include = index.get("include") or []
    exclude = index.get("exclude") or []
    if not isinstance(include, list):
        errors.append(f"{source}: index.include must be a list")
        include = []
    if not isinstance(exclude, list):
        errors.append(f"{source}: index.exclude must be a list")
        exclude = []

    if mode == "allowlist" and not include:
        errors.append(
            f"{source}: index.mode=allowlist requires a non-empty index.include "
            "(fail-closed: refusing to index the world)"
        )

    known = set(repo_names or ())
    for label, patterns in (("include", include), ("exclude", exclude)):
        for raw in patterns:
            text = _strip_quotes(str(raw))
            if not text:
                errors.append(f"{source}: index.{label} contains an empty pattern")
                continue
            match = _REPO_SCOPED_RE.match(text)
            if match and known and match.group(1) not in known:
                # Only warn when it looks like repo-scope but repo is unknown and
                # the left side is a plausible repo token (no path separators).
                left = match.group(1)
                if "/" not in left and "\\" not in left and "*" not in left:
                    errors.append(
                        f"{source}: index.{label} pattern {text!r} uses unknown "
                        f"repo name {left!r} (known: {sorted(known)})"
                    )
            try:
                compile_pattern(text, repo_names=known)
            except ValueError as exc:
                errors.append(f"{source}: index.{label}: {exc}")
    return errors


def load_index_policy(
    workspace: Path,
    manifest: dict[str, Any] | None = None,
) -> IndexPolicy:
    """Load IndexPolicy from workspace manifest + .contractmeshignore.

    Raises ValueError when ``index.mode`` is missing or invalid — no silent fallback.
    """
    from .workspace_manifest import load_workspace_manifest

    ws = workspace.resolve()
    if manifest is None:
        try:
            manifest = load_workspace_manifest(ws)
        except FileNotFoundError as exc:
            raise ValueError(
                "contractmesh.yml not found; cannot load index policy. "
                "Run: contractmesh init --here"
            ) from exc

    index = normalize_index_security(dict(manifest.get("index") or {}))
    errors = validate_index_security(
        index,
        repo_names=[
            str(r["name"])
            for r in (manifest.get("repos") or [])
            if isinstance(r, dict) and r.get("name")
        ],
        source=str(manifest.get("source") or "contractmesh.yml"),
    )
    if errors:
        raise ValueError(errors[0])

    mode_value = str(index.get("mode")).strip().lower()
    mode: IndexMode = "allowlist" if mode_value == "allowlist" else "denylist"

    repo_paths = {
        str(r["name"]): str(r.get("path") or ".")
        for r in (manifest.get("repos") or [])
        if isinstance(r, dict) and r.get("name")
    }
    known = list(repo_paths)

    include = tuple(compile_pattern(p, repo_names=known) for p in index.get("include") or [])
    exclude = tuple(compile_pattern(p, repo_names=known) for p in index.get("exclude") or [])
    ignore = load_contractmesh_ignore(ws)
    return IndexPolicy(
        workspace=ws,
        mode=mode,
        include=include,
        exclude=exclude,
        ignore=ignore,
        repo_paths=repo_paths,
    )
