# Design principles

## Engineering Knowledge Infrastructure

ContractMesh turns implicit engineering knowledge into auditable agent context.
It is the missing knowledge layer between codebases and AI agents: contracts,
architecture, integrations, known gaps, code anchors and source provenance.

## Workspace Understanding, Not Code Chat

ContractMesh exists because agents need to understand engineering workspaces,
not merely retrieve plausible chunks.

Real workspaces contain contracts, ownership boundaries, integrations, known
gaps and architecture decisions that are not obvious from source code alone.

## Contracts First

Contracts are the highest-value retrieval unit because they encode behavior,
boundaries and ownership. Code anchors are linked from contracts so the agent
can move from intent to implementation.

## Evolution-Aware Context

The first useful question is usually "where is this implemented?" The more
valuable question is "how did this behavior evolve?" ContractMesh should grow
toward linking contracts to owners, tests, ADRs, migrations, known gaps and
changelogs so agents can reason about history, not only location.

## Mental Model

```text
Contracts explain intent.
Code anchors locate implementation.
Crosslinks connect both.
Evolution links show what changed and why.
MCP exposes structured retrieval to agents.
```

## Deterministic by Default

The same workspace state should produce the same index and retrieval regression
behavior. This makes ranking drift visible and keeps the system understandable.

## Local by Default

Generated indexes live under `.contractmesh/index/` and are ignored by Git. Teams can
decide whether private indexes are safe to share.

## Agent Rules Are Product Surface

The rule file is part of the architecture. It teaches the agent how to retrieve,
when to read code directly and how to cite sources.

## Embeddings Are Support, Not Trust

Embeddings can improve recall later, but the primary source of truth should
remain contracts, architecture, explicit crosslinks and code anchors.

## Trust Boundaries

ContractMesh is an **engineering knowledge orchestrator**, not a code-intelligence
engine. Structural graphs and code search remain complementary evidence layers.
It **orchestrates** trusted docs and inferred evidence under one hierarchy.

See [trust-model.md](trust-model.md) for `source_type` and `trust_level` rules.

## Anti-Goals

ContractMesh is not:

- another vector database;
- an autonomous coding agent;
- a replacement for documentation;
- a generic semantic code search tool;
- a Spec Kit / SDD workflow replacement (Spec Kit, Kiro, and similar remain complementary);
- a **code intelligence engine** (call graphs, blast radius as primary product);
- a graph database requirement;
- a SaaS platform;
- a multi-agent orchestration framework.

## Demo Data Must Stay Fictional

The public demo should never depend on private product names, endpoints, gaps or
architecture.
