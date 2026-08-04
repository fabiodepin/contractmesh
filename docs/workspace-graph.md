# Workspace graph export

ContractMesh can export the generated knowledge layer as deterministic JSON:

```bash
contractmesh graph
```

The command reads `.contractmesh/index/search-index.manifest.json`, so run
`contractmesh index` first when docs or code anchors change.

## Format

```json
{
  "graph_version": 1,
  "schema_version": 3,
  "workspace_mapping_version": "v3",
  "nodes": [],
  "edges": []
}
```

Nodes include contracts, ADRs, code anchors, gaps and documents. Edges include
crosslinks, ownership and structural relations when enabled in `contractmesh.yml`.

## Maintainer script

```bash
bash scripts/export-workspace-graph.sh
```

This shell wrapper calls the same engine used by `contractmesh graph`.
