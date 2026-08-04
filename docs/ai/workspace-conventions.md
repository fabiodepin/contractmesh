# Workspace conventions

## Repository layout

Each repository listed in `contractmesh.yml` may provide:

```text
AGENTS.md
docs/architecture.md
docs/integrations.md
docs/known-gaps.md
docs/contracts/README.md
docs/contracts/*.md
docs/adrs/*.md
```

The indexer also reads selected source files to build code anchors.

`contractmesh.yml` is the workspace manifest. Initialize it with
`contractmesh init --here`.

## Contracts

Contracts should describe stable behavior, not implementation trivia. Prefer:

- responsibilities and non-responsibilities;
- inputs, outputs and invariants;
- cross-repo dependencies;
- known gaps with stable IDs;
- code symbols in backticks when a contract maps to source.

Example:

```md
---
id: APP-CONTRACT-001
owner:
  team: TODO
  service: example-app
  domain: example-domain
  contact: TODO
related_anchors:
  - ExampleService
---

`ExampleService` owns the core example behavior for this workspace.
```

## Ownership

Ownership is optional but strongly recommended for contracts, ADRs and important
context docs. It lets agents answer who owns a rule and who should be consulted
before changing it.

```yaml
owner:
  team: TODO
  service: example-app
  domain: example-domain
  contact: TODO
```

## ADRs

Use `docs/adrs/*.md` for Architecture Decision Records. Contracts explain
behavior and domain intent. ADRs explain architectural decisions, trade-offs and
why a boundary exists.

```md
---
id: ADR-APP-001
title: Example service boundary
status: accepted
owner:
  team: TODO
  service: example-app
  domain: example-domain
  contact: TODO
related_contracts:
  - APP-CONTRACT-001
related_anchors:
  - ExampleService
---

# ADR-APP-001: Example service boundary
```

## Known gaps

Use stable IDs that include the domain prefix:

```text
APP-KG-001
WEB-KG-001
API-KG-001
```

Do not reuse IDs after deleting a gap. Mark old gaps as closed instead.

## Generated files

Files under `.contractmesh/` are local artifacts and should not be committed.
Rebuild the index after changing docs, contracts or indexed source files:

```bash
contractmesh index
```

Bootstrap suggestions are draft-only under `.contractmesh/generated/`.

## Agent rules

Agent rules should explain how to use the knowledge layer, not only where files
live. See `.cursor/rules/workspace-knowledge.mdc` for the default flow.
