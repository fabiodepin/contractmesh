# Open-source release transition

> **Historical note.** This page records the completed open-source transition.
> For current priorities, see [ROADMAP.md](../ROADMAP.md).

ContractMesh ships as an **installed tool** with **external workspaces**:

- `pipx install "contractmesh[mcp]"` and `contractmesh init --here`
- generic workspace docs and `templates/basic/` starter
- deterministic index generation under `.contractmesh/`
- MCP retrieval tools
- retrieval regression tests via `tests/fixtures/basic-workspace/`

## Completed

### Package the CLI

```bash
pipx install "contractmesh[mcp]"
cd my-project
contractmesh init --here
contractmesh index
contractmesh mcp
```

### Mature configuration

`contractmesh.yml` is the sole workspace manifest. Legacy shell manifest files
are removed from the public surface.

## Follow-up improvements

### Make taxonomy configurable

Move kind weights, code-anchor language rules and optional ranking boosts into
configuration files.

### Add CI templates

Provide GitHub Actions / GitLab CI snippets that run `contractmesh check` on
user workspaces.

### Package distribution

ContractMesh is published on PyPI with the optional `[mcp]` extra. Future
releases should continue validating both standard package installation and the
recommended `pipx install "contractmesh[mcp]"` path.

See [ROADMAP.md](../ROADMAP.md) for feature milestones (trust model, drift, bootstrap).
