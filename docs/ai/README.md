# ContractMesh AI knowledge map

This directory documents the workspace knowledge model used by ContractMesh.
Each project keeps its own `AGENTS.md` and `docs/` folders; this directory
describes the conventions, schemas and cross-repo map for multi-repo workspaces
such as `example-app`.

## Core idea

ContractMesh turns explicit engineering knowledge into an auditable retrieval
layer for agents:

```text
question
-> contracts / architecture / known gaps
-> related code anchors
-> chunks
-> cited sources
```

The index is local and generated under `.contractmesh/index/`.

## Files

| File | Purpose |
| --- | --- |
| [repositories.md](repositories.md) | Repository roles and links to per-repo AI docs. |
| [ecosystem-map.md](ecosystem-map.md) | Workspace dependency map and flow notes. |
| [glossary.md](glossary.md) | Terms used by the knowledge model. |
| [cross-repo-impact.md](cross-repo-impact.md) | Review checklist for changes that cross boundaries. |
| [workspace-conventions.md](workspace-conventions.md) | How to structure docs, contracts, gaps and generated files. |
| [search-index.schema.json](search-index.schema.json) | Lightweight schema for generated index files. |

## Knowledge index

Build:

```bash
contractmesh index
```

Search (CLI or MCP `fetch_hits`):

```bash
contractmesh status
# MCP: fetch_hits("example service greeting", kind=["contract"])
# MCP: fetch_hits(gap="APP-KG-001")
# MCP: fetch_hits("ExampleService", kind=["code_anchor"], include_main_chunk=false)
```

Generated artifacts:

| File | Purpose |
| --- | --- |
| `.contractmesh/index/search-index.manifest.json` | Portable metadata: docs, anchors, kinds, gaps and crosslinks. |
| `.contractmesh/index/search-index.local.json` | Machine-local paths and hashes. |
| `.contractmesh/index/chunks/` | JSONL chunk files. |

## Indexed kinds

| Kind | Meaning |
| --- | --- |
| `agents` | Repository-specific agent instructions. |
| `contract` | Stable behavior contracts under `docs/contracts/`. |
| `architecture` | Architecture notes. |
| `integrations` | Cross-system integration notes. |
| `adr` | Architecture Decision Records under `docs/adrs/`. |
| `known_gaps` | Open gaps, risks or validation items. |
| `workspace_doc` | Docs from the workspace root. |
| `code_anchor` | Source-level classes, services, clients, configs or exported functions. |
| `test_anchor` | Test files/functions related to contracts or code anchors. |
| `openapi_spec` | Optional generated OpenAPI evidence. |

## MCP tools

| Tool | Use |
| --- | --- |
| `index_status` | Call first. Checks age, missing chunks and rebuild recommendation. |
| `fetch_hits` | Main retrieval call. Returns metadata, text and related anchors. |
| `impact_analysis` | Builds a Change Impact Graph with contracts, ADRs, owners, anchors, tests and gaps. |
| `preflight_change` | Compact preflight card (`card.text`) + `details` JSON; soft block via `agent_policy` on HIGH risk. |
| `related_tests` | Finds tests related to a behavior query or code symbol. |
| `orient_workspace` | Summarizes services, routes, layers and top contracts from indexed evidence. |
| `list_drift` | Lists optional drift findings when `index.drift` is enabled. |
| `evolution_trace` | Traces optional evolution links when `index.git_mining` is enabled. |
| `search_docs` | Metadata-only search. Useful for broad exploration. |
| `get_chunk` | Fetch one chunk by id after truncation. |
| `get_doc_chunks` | Fetch several chunks from a stable `doc_id`. |
| `list_gaps` | Browse known gaps by id, prefix or repo. |
| `pr_impact` | Map a git diff/PR to contracts, ADRs, anchors, tests, gaps and documentation impact. |
| `branch_context` | Current branch, local changes and related contracts before commit/PR. |
| `suggest_tests_for_diff` | Suggest indexed tests and commands for changed files. |
| `documentation_impact` | Evidence-based docs review (`none` / `possible` / `confirmed`). |
| `docs_drift_check` | Deprecated alias of `documentation_impact`. |

Do not persist `chunk_id` values in human docs. Use stable `doc_id` or `path`;
chunk suffixes can change after rebuilds.

### Git-aware tools (read-only)

Before opening a PR:

```text
pr_impact(base="main", head="HEAD", include_worktree=false)
```

Expected top-level fields:

- `changed_files[]`
- `contracts[]`, `adrs[]`, `code_anchors[]`, `test_anchors[]`, `known_gaps[]`
- `suggested_test_commands[]`
- `docs_possibly_stale[]`
- `provenance`

## Code anchors and crosslinks

The indexer creates `code_anchor` entries from selected Java, TypeScript, Go,
Python and YAML files. It also creates `test_anchor` entries from common test
locations. Contract, architecture and integration docs are scanned for
symbols such as `ExampleService`. When a symbol is found in the same repository,
the document gets `code_anchors[]` and the anchor gets `related_doc_ids[]`.

Contracts and ADRs may define `owner` front matter. ADRs may also define
`related_contracts` and `related_anchors`, which lets `impact_analysis` group
the likely impact of a rule change by owner, service, ADR, implementation and
validation evidence.

This is the key difference from generic chunk search: the agent can show the
contract it used and the code anchors related to that contract.
