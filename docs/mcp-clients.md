# MCP client setup

ContractMesh exposes the local workspace knowledge layer over MCP stdio. The
server is read-only by default: it exposes retrieval context, source provenance,
impact analysis and related tests. It does not edit code.

Install ContractMesh, then initialize and index the project you want the client
to understand:

```bash
pipx install "contractmesh[mcp]"
cd /path/to/your-project
contractmesh init --here
# edit contractmesh.yml allowlist for your real roots, then:
contractmesh index
```

Default `init` is non-invasive (no example source or demo contracts). Add
`--with-examples` only for a throwaway scaffold demo.
The examples below assume that `contractmesh` is available on `PATH`. Set `cwd`
to the initialized project—not to the ContractMesh source repository.
If a desktop client does not inherit your shell `PATH`, replace `contractmesh`
with the absolute path reported by `command -v contractmesh`.

## Generic stdio config

```json
{
  "mcpServers": {
    "contractmesh": {
      "command": "contractmesh",
      "args": ["mcp"],
      "cwd": "/path/to/your-project"
    }
  }
}
```

## Cursor

Cursor can use an MCP server definition like:

```json
{
  "mcpServers": {
    "contractmesh": {
      "command": "contractmesh",
      "args": ["mcp"],
      "cwd": "/path/to/your-project"
    }
  }
}
```

Maintainers working from this repository can generate a local Cursor
configuration with:

```bash
bash scripts/write-mcp-cursor-config.sh
```

## Claude Code / Claude Desktop

Use the same stdio shape:

```json
{
  "mcpServers": {
    "contractmesh": {
      "command": "contractmesh",
      "args": ["mcp"],
      "cwd": "/path/to/your-project"
    }
  }
}
```

## Gemini CLI

Project-level settings can point to the local CLI:

```json
{
  "mcpServers": {
    "contractmesh": {
      "command": "contractmesh",
      "args": ["mcp"],
      "cwd": "/path/to/your-project"
    }
  }
}
```

## Cline / Roo

Use a stdio-compatible MCP server entry:

```json
{
  "mcpServers": {
    "contractmesh": {
      "command": "contractmesh",
      "args": ["mcp"],
      "cwd": "/path/to/your-project"
    }
  }
}
```

## Tool Surface

| Tool | Use |
| --- | --- |
| `index_status` | Check index health before retrieval. |
| `fetch_hits` | Retrieve grounded docs, chunks and related anchors. |
| `impact_analysis` | Build a Change Impact Graph with contracts, ADRs, owners, anchors, tests and gaps before changing behavior. |
| `preflight_change` | Preflight card before editing a symbol (contracts, gaps, tests, drift, risk). |
| `related_tests` | Find tests related to a behavior query or symbol. |
| `orient_workspace` | Summarize services, routes, layers, and top contracts; structural evidence is inferred. |
| `list_drift` | List optional drift findings when `index.drift` is enabled. |
| `evolution_trace` | Trace optional evolution links when `index.git_mining` is enabled. |
| `pr_impact` | Map git diff/PR to contracts, ADRs, anchors, tests, gaps and documentation impact. |
| `branch_context` | Branch + local changes + related contracts. |
| `suggest_tests_for_diff` | Tests and commands for changed files. |
| `documentation_impact` | Evidence-based docs review (`none` / `possible` / `confirmed`). |
| `docs_drift_check` | Deprecated alias of `documentation_impact`. |
| `list_gaps` | Browse known gaps by id, prefix or repo. |
| `search_docs` | Explore metadata-only hits. |
| `get_chunk` / `get_doc_chunks` | Deepen retrieval when results are truncated. |

## Security Notes

- The MCP server runs locally over stdio.
- It exposes indexed context and retrieval evidence, not write operations.
- Do not index secrets, tokens, customer data or private endpoints.
- Use `.contractmeshignore` to exclude sensitive files and generated artifacts.
- Review docs and generated context before sharing agent logs externally.
- Generated local indexes live under `.contractmesh/index/` and are ignored by Git.

See [Security and privacy](security-privacy.md) for the full model and current
limitations.
