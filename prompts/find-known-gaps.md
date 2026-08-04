# ContractMesh Known Gaps Discovery Prompt

You are discovering candidate known gaps for ContractMesh.

Known gaps are reviewable risk notes for agents. They are not accusations and
they are not automatically true. Do not edit files automatically unless the user
explicitly approves.

## Goals

Analyze the workspace for evidence of:

- TODO comments;
- FIXME comments;
- skipped or missing tests;
- docs that mention incomplete behavior;
- contracts with unresolved TODO fields;
- ADR consequences that need follow-up;
- integration boundaries without validation;
- code paths that appear important but have weak documentation.

## Required Workflow

1. Inspect docs, contracts, ADRs and tests.
2. Search for `TODO`, `FIXME`, `HACK`, `XXX`, `skip`, `pending` and similar
   markers.
3. Compare important contracts with available tests when practical.
4. Produce candidate known gaps grouped by confidence.
5. Wait for human approval before writing or updating known-gap files.

## Rules

- Never assert gaps as absolute truth.
- Do not invent missing tests if evidence is weak.
- Cite evidence for every candidate.
- Use confidence levels: high, medium, low.
- Prefer fewer, clearer gaps over a noisy list.
- Include suggested owner only when there is evidence.
- Respect `.contractmeshignore`.

## Suggested Known Gap Shape

```markdown
| Gap ID | Status | Description |
| --- | --- | --- |
| APP-KG-001 | Open | Concise description supported by repository evidence. |
```

Use the `{PREFIX}-KG-{NNN}` ID convention. Report confidence, evidence, impact,
and suggested validation in the review output before adding a row to the
canonical known-gap file.

## Output Format

```text
High confidence
- id: ...
  title: ...
  evidence: ...
  impact: ...
  suggested validation: ...

Medium confidence
- ...

Low confidence
- ...

Files to update after approval
- ...
```
