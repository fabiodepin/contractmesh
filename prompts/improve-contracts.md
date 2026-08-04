# ContractMesh Contract Review Prompt

You are reviewing existing ContractMesh contracts.

Do not edit files automatically. Analyze the current contracts and return
suggestions for human review.

## Goals

Find opportunities to improve:

- missing owner metadata;
- missing or weak contract IDs;
- unclear contract status;
- ambiguous domain language;
- missing related anchors;
- missing related ADRs;
- missing known gap references;
- duplicate or overlapping contracts;
- contracts that describe implementation details instead of behavior;
- contracts that appear to invent behavior without evidence.

## Required Workflow

1. Inspect `contractmesh.yml`.
2. Inspect workspace-level and repo-local contracts.
3. Inspect ADRs, architecture docs, integrations docs and known gaps.
4. Inspect related code anchors only when needed to validate crosslinks.
5. Return a review report. Do not change files unless the user explicitly asks.

## Rules

- Do not invent missing business rules.
- Mark uncertainty clearly.
- Use confidence levels: high, medium, low.
- Prefer concrete suggestions with file paths.
- Separate correctness issues from polish suggestions.

## Output Format

```text
Summary
- ...

High-priority issues
- file: ...
  issue: ...
  evidence: ...
  suggestion: ...
  confidence: high|medium|low

Missing ownership
- file: ...
  suggested owner fields: ...
  evidence: ...
  confidence: high|medium|low

Missing crosslinks
- contract: ...
  suggested related_anchors: ...
  evidence: ...
  confidence: high|medium|low

Potential duplicates
- contracts: ...
  overlap: ...
  recommendation: ...
  confidence: high|medium|low

Do not change automatically
- list the files that would need human-approved edits
```
