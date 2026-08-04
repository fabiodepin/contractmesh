# Contributing

Thanks for helping improve ContractMesh.

## Development setup

ContractMesh development requires Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[mcp]"
```

## Development loop

```bash
contractmesh self check
contractmesh check --release   # source checkout / CI only
```

For debugging individual checks:

```bash
python3 -m unittest scripts.lib.test_fetch_hits
bash scripts/test-mcp-workspace-knowledge.sh
bash scripts/test-preflight-smoke.sh
```

Run `contractmesh check --release` for the complete maintained test set and
release validation.

## Project principles

ContractMesh separates facts from inferences.

Contracts, ADRs, and known gaps are explicit engineering knowledge. Graphs,
mining, and embeddings are evidence.

Features must preserve this trust hierarchy. Do not blur the line between what
the system knows, what it infers, and what humans have confirmed.

## Contribution guidelines

- Keep retrieval behavior deterministic unless a feature is explicitly optional.
- Add or update retrieval regression tests when ranking expectations change.
- Prefer explicit contracts, ownership metadata and code anchors over hidden heuristics.
- Agent-facing features should preserve source provenance whenever practical.
- Bootstrap suggestions must always be emitted as draft artifacts.
- Inferred knowledge must never be promoted automatically to confirmed contracts.
- Keep example data fictional (`example-app`, `ScreenFlow`, etc.).
- Do not commit generated files under `.contractmesh/`.

## Pull request checklist

- Docs updated when behavior changes.
- Tests added or updated for index, search or MCP behavior.
- `contractmesh check --release` passes.
- `contractmesh index` reports zero unresolved contract symbols for the basic
  fixture when contracts reference indexed anchors.
