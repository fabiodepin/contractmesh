#!/usr/bin/env python3
"""Keyword search over the local workspace knowledge index."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .workspace_search import (
    IndexNotFoundError,
    get_workspace_root,
    load_index,
    resolve_gap_exact,
    resolve_symbol_exact,
    run_build,
    search_documents,
    search_hit_to_dict,
    tokenize_query,
)


def format_gaps(gaps: list[str], gap_exact: str | None) -> str:
    if not gaps:
        return "-"
    if gap_exact and gap_exact in gaps:
        return gap_exact
    return ",".join(gaps[:3])


def open_in_editor(path: Path) -> bool:
    path_s = str(path.resolve())
    gui_cmds: list[list[str]] = []
    if shutil.which("cursor"):
        gui_cmds.append(["cursor", "-g", path_s])
    if shutil.which("code"):
        gui_cmds.append(["code", "-g", path_s])

    for cmd in gui_cmds:
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            print(f"[open] {' '.join(cmd)}", file=sys.stderr)
            return True
        except OSError:
            continue

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if editor:
        try:
            cmd = shlex.split(editor) + [path_s]
            subprocess.run(cmd, check=False)
            print(f"[open] {editor} {path_s}", file=sys.stderr)
            return True
        except OSError:
            pass

    if shutil.which("vim"):
        try:
            subprocess.run(["vim", path_s], check=False)
            print(f"[open] vim {path_s}", file=sys.stderr)
            return True
        except OSError:
            pass

    print(
        "[WARN] no editor found (tried cursor, code, $EDITOR, vim)",
        file=sys.stderr,
    )
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Search workspace knowledge index")
    parser.add_argument("query", nargs="*", help="Search terms")
    parser.add_argument("--repo", action="append", default=[], help="Filter by repo")
    parser.add_argument("--kind", action="append", default=[], help="Filter by kind")
    parser.add_argument(
        "--gap",
        metavar="ID",
        help="Search by known-gap ID (exact match in indexed known_gap_ids)",
    )
    parser.add_argument(
        "--symbol",
        metavar="NAME",
        help="Search code_anchor by class/type name (exact or partial *Impl)",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--limit", type=int, default=20, help="Max results")
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open first hit in cursor, code, $EDITOR, or vim",
    )
    parser.add_argument(
        "--rebuild-if-missing",
        action="store_true",
        help="Run build-search-index.sh if manifest is missing",
    )
    args = parser.parse_args()

    workspace = get_workspace_root()

    try:
        manifest, local_by_id = load_index(workspace)
    except IndexNotFoundError:
        if args.rebuild_if_missing:
            run_build(workspace)
            try:
                manifest, local_by_id = load_index(workspace)
            except IndexNotFoundError:
                print("[FAIL] search index not found.", file=sys.stderr)
                print("Run: bash scripts/build-search-index.sh", file=sys.stderr)
                return 1
        else:
            print("[FAIL] search index not found.", file=sys.stderr)
            print("Run: bash scripts/build-search-index.sh", file=sys.stderr)
            return 1

    query = " ".join(args.query).strip()
    gap_exact = resolve_gap_exact(query, args.gap)
    symbol_exact = resolve_symbol_exact(query, args.symbol)

    repo_arg: str | list[str] | None = args.repo if args.repo else None
    kind_arg: str | list[str] | None = args.kind if args.kind else None

    hits, message = search_documents(
        workspace,
        manifest,
        local_by_id,
        query=query,
        gap=args.gap,
        symbol=args.symbol,
        repo=repo_arg,
        kind=kind_arg,
        limit=args.limit,
    )

    if message:
        print(f"[FAIL] {message}", file=sys.stderr)
        return 1

    stale_count = sum(1 for h in hits if h.stale)
    chunks_missing_count = sum(1 for h in hits if h.chunks_missing)

    first_abs_path: Path | None = None

    for hit in hits:
        abs_path = workspace / hit.path
        if first_abs_path is None and abs_path.is_file():
            first_abs_path = abs_path

        if not args.json:
            kind_s = hit.kind or "doc"
            gaps_s = format_gaps(hit.known_gap_ids, gap_exact)
            sym_s = f" symbol={hit.symbol}" if hit.symbol else ""
            print(f"[{kind_s}] {hit.path}{sym_s}")
            print(f"  score={hit.score} gaps={gaps_s}")
            if hit.snippet:
                print(f"  {hit.snippet}")
            print()

    if args.json:
        legacy_rows = []
        for hit in hits:
            legacy_rows.append(
                {
                    **search_hit_to_dict(hit),
                    "gaps": hit.known_gap_ids,
                }
            )
        print(json.dumps(legacy_rows, indent=2, ensure_ascii=False))

    if args.open:
        if first_abs_path and first_abs_path.is_file():
            open_in_editor(first_abs_path)
        elif hits:
            print("[WARN] first hit file not found on disk", file=sys.stderr)

    if stale_count:
        print(
            f"[WARN] local index may be stale for {stale_count} documents. "
            "Run: bash scripts/build-search-index.sh",
            file=sys.stderr,
        )
    if chunks_missing_count:
        print(
            f"[WARN] chunks missing for {chunks_missing_count} hits. "
            "Run: bash scripts/build-search-index.sh",
            file=sys.stderr,
        )

    if not hits and (tokenize_query(query) or gap_exact or symbol_exact):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
