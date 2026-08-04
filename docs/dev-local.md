# Local development (ContractMesh tool)

Develop and test the ContractMesh CLI and engine in this repository.

> **Audience:** contributors and maintainers of ContractMesh itself. To use
> ContractMesh in another project, start with the main
> [README](../README.md#use-in-your-project).

## Prerequisites

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[mcp]"
```

## Maintainer checks

```bash
contractmesh self check
contractmesh check --release
```

`check --release` runs the full autonomous smoke: fixture index, unit tests, and
CLI validation. It is **only available in the ContractMesh source repository**
(maintainer/CI). Installed wheels should use `contractmesh self check` instead.

## Work on a sample workspace

Use the bundled fixture or create an external workspace:

```bash
export CONTRACTMESH_WORKSPACE="$(pwd)/tests/fixtures/basic-workspace"
contractmesh index
contractmesh status
contractmesh check
contractmesh mcp
```

Or initialize a fresh workspace under `/tmp`:

```bash
mkdir -p /tmp/cm-test && cd /tmp/cm-test
contractmesh init --here --template basic
contractmesh index
contractmesh status
contractmesh check
```

## MCP

```bash
export CONTRACTMESH_WORKSPACE=/path/to/your/workspace
contractmesh mcp
```

In Cursor, call `index_status` first, then `fetch_hits` or `orient_workspace`.

## Feature flags

Edit `contractmesh.yml` `index:` block in your workspace:

- `structural_graph: true` — routes and controller/service/repository edges
- `drift: true` — drift findings in manifest + `list_drift` MCP
- `git_mining: true` — evolution links + `evolution_trace` MCP

Rebuild after changing flags: `contractmesh index`.

## Bootstrap suggest

```bash
contractmesh bootstrap --suggest --index
```

Review `.contractmesh/generated/bootstrap-suggestions/suggestions.json` before
promoting any draft to `confirmed`.

## Retrieval regression

```bash
python3 -m unittest scripts.lib.test_mcp_golden_queries
```

Expected top contract for the basic fixture: `APP-CONTRACT-001`.
