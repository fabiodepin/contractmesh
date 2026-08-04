# ContractMesh Monorepo Bootstrap Prompt

You are helping bootstrap ContractMesh for a monorepo.

ContractMesh is a local-first, contracts-first engineering knowledge layer for
AI coding agents. Before drafting files manually, run `contractmesh bootstrap
--suggest` and review `.contractmesh/generated/bootstrap-suggestions/`
(draft-only).
Your task is to detect the monorepo structure and propose an
initial ContractMesh knowledge layer. Do not create an autonomous agent and do
not add external AI dependencies.

## Monorepo Discovery Goals

Inspect the workspace and identify:

- services;
- apps;
- packages and shared libraries;
- domains;
- ownership boundaries;
- integration boundaries;
- tests that validate important behavior;
- existing docs, ADRs, README files and architecture notes.

## Required Workflow

1. Inspect the repository tree and common monorepo files such as package
   manifests, workspace configs, build files, service directories and app
   directories.
2. Produce a plan before writing files.
3. Include a proposed `contractmesh.yml` that maps logical repo names to local
   paths, even when everything lives inside one Git repository.
4. For each detected app, service or library, report:
   - path;
   - role;
   - domain;
   - likely owner;
   - inbound dependencies;
   - outbound dependencies;
   - confidence.
5. Propose contracts for stable domain boundaries.
6. Propose ADRs for important boundaries and trade-offs.
7. Propose known gaps only when there is evidence.
8. Wait for human approval before writing files.

## Rules

- Do not invent business rules.
- Do not turn dependency guesses into contracts without evidence.
- Mark uncertain ownership, behavior and integrations as `TODO`.
- Prefer a small number of high-value contracts over many thin contracts.
- Separate product apps, backend services and shared libraries clearly.
- Shared libraries can have contracts when they enforce important behavior.
- Do not modify application code unless explicitly asked.
- Respect `.contractmeshignore`.

## Files To Generate After Approval

- `contractmesh.yml`;
- `docs/contracts/*.md` for workspace-level contracts, or package-local
  contract roots declared in `contractmesh.yml` when ownership is clearly local;
- `docs/adrs/*.md` for monorepo-level decisions, or package-local
  `docs/adrs/*.md` when the decision belongs to one service;
- `docs/known-gaps.md` or package-local gap paths declared in `contractmesh.yml`;
- optional `docs/architecture.md` or `docs/integrations.md` when helpful.

All `docs` paths in `contractmesh.yml` are relative to each corresponding
`repos[].path`. Include a `path: .` repository when workspace-level documents
live at the monorepo root.

## Output Format

```text
Plan
- ...

Monorepo map
- path: apps/admin-web
  type: app
  domain: TODO
  owner: TODO
  inbound: []
  outbound: []
  evidence: ...
  confidence: high|medium|low

Proposed contracts
- id: ...
  title: ...
  evidence: ...
  confidence: high|medium|low

Proposed ADRs
- id: ...
  title: ...
  evidence: ...
  confidence: high|medium|low

Known gaps candidates
- id: ...
  evidence: ...
  confidence: high|medium|low

Files to write after approval
- ...
```
