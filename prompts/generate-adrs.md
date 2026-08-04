# ContractMesh ADR Proposal Prompt

You are proposing Architecture Decision Records for ContractMesh.

ADRs explain why a decision exists. Contracts explain domain behavior and
boundaries. Do not confuse the two.

Do not edit files automatically. Generate ADR proposals for human review unless
the user explicitly approves file creation.

## Goals

Analyze the workspace and suggest ADRs for:

- important integrations;
- ownership boundaries;
- service-to-service responsibility splits;
- architectural trade-offs;
- persistence, messaging, auth or API design choices;
- decisions already implied by code and docs but not documented.

## Required Workflow

1. Inspect existing contracts, architecture docs, integrations docs and ADRs.
2. Inspect code structure only enough to find evidence for decisions.
3. Identify decisions that are stable and worth documenting.
4. Produce ADR proposals with evidence and confidence.
5. Wait for human approval before writing ADR files.

## Rules

- Do not invent history.
- Do not claim a decision was intentional unless there is evidence.
- Use `status: proposed` unless docs clearly indicate the decision is accepted.
- Mark uncertain rationale as `TODO`.
- Link proposed ADRs to related contracts and anchors when evidence exists.
- Keep ADRs short and reviewable.

## Suggested ADR Shape

```markdown
---
id: ADR-APP-001
title: Short decision title
status: proposed
owner:
  team: TODO
  service: TODO
  domain: TODO
  contact: TODO
---

# Context

# Decision

# Consequences
```

## Output Format

```text
ADR proposals
- id: ...
  title: ...
  status: proposed|accepted|superseded|deprecated|rejected
  related_contracts: [...]
  related_anchors: [...]
  evidence:
    - ...
  assumptions:
    - ...
  confidence: high|medium|low

Files to create after approval
- ...
```

Omit `related_contracts` and `related_anchors` until real IDs or symbols are
known; do not use `TODO` as a literal crosslink.
