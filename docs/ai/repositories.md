# Workspace repositories

> **Example workspace stub.** Replace this map with the repositories from your
> own `contractmesh.yml` after `contractmesh init --here`.

ContractMesh indexes one or more repositories listed in `contractmesh.yml`.
This file documents the workspace map for agent retrieval and cross-repo review.

| Repository | Role | AI docs |
| --- | --- | --- |
| **app** | Example application (`example-app`) | `AGENTS.md`, `docs/contracts/` |
| **web** | Optional web client (when present) | `AGENTS.md`, `docs/contracts/` |

Replace the table with your real repositories after `contractmesh init --here`.

## Per-repo expectations

Each indexed repository should provide:

- `AGENTS.md` — agent instructions for that repo
- `docs/contracts/*.md` — stable behavior contracts
- `docs/adrs/*.md` — architecture decisions (optional)
- `docs/known-gaps.md` — open gaps with stable IDs

See [workspace conventions](workspace-conventions.md) for front matter and naming.

## Single-repo workspaces

For a single project, set `repos` to one entry with `path: .` and `name` matching
your package or service id (for example `app` or `my-project`).
