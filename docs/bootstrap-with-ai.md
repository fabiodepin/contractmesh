# Bootstrap with AI

The recommended way to adopt ContractMesh is to install the CLI and configure
your **existing project** with your AI coding agent.

ContractMesh does not ship an autonomous agent and does not call external APIs.
Official prompts help Cursor, Claude Code, Gemini CLI, Cline, Roo, and other
agents propose an initial ContractMesh structure.

> **Trust:** ContractMesh can suggest knowledge, but only humans can confirm it.

## Recommended flow

1. Install ContractMesh (`pipx install "contractmesh[mcp]"` or `pip install "contractmesh[mcp]"`).
2. `cd` into your project (for example `my-project`).
3. Run `contractmesh init --here` (or let the agent run it).
4. Optional draft suggestions:

```bash
contractmesh bootstrap --suggest
```

Review `.contractmesh/generated/bootstrap-suggestions/suggestions.json`.
Never copy drafts into `docs/contracts/` without human review.

5. Paste a bootstrap prompt from [prompts/](../prompts/).
6. Review every contract, ADR, and known gap.
7. Build and validate:

```bash
contractmesh index
contractmesh status
contractmesh check
contractmesh mcp
```

See [MCP client setup](mcp-clients.md) for Cursor and other clients.

## Quick prompt

```text
I want to adopt ContractMesh in this workspace.
If ContractMesh is not initialized, run: contractmesh init --here

Analyze the repository structure and propose:
- contractmesh.yml
- docs/contracts/
- docs/adrs/
- docs/known-gaps.md

Show a plan before writing files.
Mark uncertain findings as TODO.
```

## Layout

Generated indexes live under `.contractmesh/index/`.
Draft bootstrap output lives under `.contractmesh/generated/`.

Do not move your repositories into the ContractMesh tool repository.
Point `contractmesh.yml` at paths inside your project.
