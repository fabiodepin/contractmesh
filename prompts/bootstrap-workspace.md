# ContractMesh Bootstrap Prompt

You are helping bootstrap ContractMesh for this workspace.

ContractMesh is a local-first, contracts-first engineering knowledge layer for
AI coding agents. Before drafting files manually, run `contractmesh bootstrap
--suggest` and review `.contractmesh/generated/bootstrap-suggestions/`
(draft-only).
Your job is to propose and, after approval, create an initial
workspace knowledge structure. Do not create an autonomous agent, do not add
external AI dependencies and do not call external services.

## Goals

Analyze the workspace and create an initial ContractMesh structure that helps AI
coding agents understand:

- services and modules;
- domains and ownership boundaries;
- domain contracts;
- architecture decisions;
- integrations;
- known gaps;
- crosslinks between docs and code.

## Required Workflow

1. Inspect the repository tree, existing docs, package manifests, service
   folders, application entrypoints, tests and configuration files.
2. Produce a written plan before writing files.
3. In the plan, include:
   - detected services or modules;
   - inferred domains;
   - proposed owners;
   - proposed contracts;
   - proposed ADRs;
   - proposed known gaps;
   - assumptions;
   - confidence for each inference: high, medium or low.
4. Wait for human approval before writing or changing files.
5. After approval, create or update:
   - `contractmesh.yml`;
   - contract files under each configured contract root (typically `docs/contracts/*.md`);
   - `docs/adrs/*.md` or repo-local `docs/adrs/*.md`;
   - known-gap files under each configured gap path (typically `docs/known-gaps.md`);
   - relevant architecture or integration docs when obvious.
6. Keep generated docs concise and reviewable.
7. Tell the user to run:

```bash
contractmesh index
contractmesh status
contractmesh check
contractmesh mcp
```

## Rules

- Do not invent business rules.
- Do not present guesses as facts.
- Mark uncertain behavior as `TODO`.
- Explain every important assumption.
- Prefer explicit owner metadata when there is evidence.
- If ownership is unclear, use `TODO` fields and explain why.
- Do not add secrets, tokens, internal credentials or customer data to docs.
- Respect `.contractmeshignore`.
- Do not modify production code unless the user explicitly asks.
- Do not implement new ContractMesh features.

## Suggested Contract Front Matter

```yaml
---
id: APP-CONTRACT-001
title: Short contract title
status: draft
owner:
  team: TODO
  service: TODO
  domain: TODO
  contact: TODO
related_anchors:
  - TODO
---
```

## Suggested ADR Front Matter

```yaml
---
id: ADR-APP-001
title: Short architecture decision title
status: proposed
owner:
  team: TODO
  service: TODO
  domain: TODO
  contact: TODO
related_contracts:
  - APP-CONTRACT-001
---
```

## Output Format

First response:

```text
Plan
- ...

Detected services/modules
- name: ...
  evidence: ...
  confidence: high|medium|low

Proposed files
- path: ...
  purpose: ...

Assumptions and TODOs
- ...
```

Only write files after the human approves the plan.
