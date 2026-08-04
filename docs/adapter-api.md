# Adapter API

ContractMesh orchestrates external code-intelligence engines without owning them.
Adapters normalize foreign graphs into structural edges with `trust_level: inferred`.

## Input contract

See [structural-adapter.schema.json](ai/structural-adapter.schema.json).

Adapters return:

- `adapter_id` — e.g. `codebase_memory`, `fog_context`, `custom`
- `edges[]` — normalized structural edges
- optional `nodes[]` — symbols referenced by edges

Each edge must include:

| Field | Value |
| --- | --- |
| `edge_type` | `imports`, `implements_route`, `uses_service`, `uses_repository`, or adapter-specific |
| `source` | Symbol or module id |
| `target` | Symbol, route, or module id |
| `repo` | Repository name from `contractmesh.yml` |
| `source_type` | `adapter` |
| `trust_level` | `inferred` |

## Registration

List adapter ids under `index.adapters` in `contractmesh.yml`:

```yaml
index:
  adapters:
    - null
```

The built-in `null` adapter is a no-op stub for tests.

## Rules

1. Adapters never promote edges to `confirmed`.
2. Conflicts with contracts surface as drift or gaps, not silent overrides.
3. Deep call graphs belong in adapters, not the ContractMesh core.

## Stub

Implementation: `contractmesh/engine/adapters/null_adapter.py`
