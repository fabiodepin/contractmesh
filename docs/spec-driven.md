# Spec-driven development and ContractMesh

Spec-driven development (SDD) is highly relevant to ContractMesh — not as a
direct competitor, but as a trend that validates the same thesis: agents need
explicit engineering intent, not vibe coding alone.

Tools such as GitHub Spec Kit, Kiro, and OpenSpec organize how a proposed change
becomes an implementation. Spec Kit’s core flow is broader than a one-off
feature brief:

```text
constitution → specify → plan → tasks → implement → analyze / converge
```

It can encode durable project principles (constitution), living specs,
organizational presets, artifact consistency checks, brownfield evolution
models, and extensions. That overlaps with parts of “what a change must not
violate.” A shallow split — “Spec Kit only describes the feature; ContractMesh
only stores permanent rules” — is therefore easy to contest.

ContractMesh does **not** replace that workflow. It is an independent knowledge
layer with typed trust and provenance over heterogeneous engineering sources.

## Essential difference

> **Spec Kit drives the change. ContractMesh grounds the change.**

More precisely: Spec Kit (and similar SDD tools) structure how a proposed change
becomes an implementation. ContractMesh provides the independent trust and
provenance layer that grounds the change in existing engineering knowledge and
repository evidence — regardless of which tool authored the proposal.

| Dimension | Spec Kit / SDD | ContractMesh |
|---|---|---|
| Primary product | Spec-driven development workflow | Knowledge and retrieval layer |
| Input | Intention for a feature or change | Existing workspace knowledge and evidence |
| Process | Constitution → spec → plan → tasks → implementation → converge | Ingest → classify → index → retrieve → impact / drift |
| Canonical artifacts | Workflow-owned (constitution, spec, plan, tasks, contracts/) | Heterogeneous sources — explicit and inferred |
| Permanent rules | Constitution, presets, living specs | Contracts, ADRs, gaps, owners, boundaries |
| Typed trust | Not the primary axis | Central to the model |
| Provenance | Traceability among SDD artifacts | Uniform provenance across knowledge, code, OpenAPI, graph, and other sources |
| Inferred evidence | Agents inspect code and context | Evidence is explicitly separated from confirmed knowledge |
| Runtime retrieval | Commands, skills, and agent prompts | Dedicated MCP tools |
| Scope security | Workflow files and integrations | Central allowlist-first, fail-closed policy |
| Cross-repo | Extensible | Native to the workspace thesis |
| Goal | Drive the change | Inform and constrain any agent or workflow |

Public formulations that remain safe:

- Specs describe the proposed change. ContractMesh grounds it in existing
  engineering knowledge and evidence.
- Spec-driven tools may encode project principles, feature requirements, plans,
  and organizational constraints. ContractMesh complements them by retrieving
  heterogeneous engineering knowledge and repository evidence through a shared
  trust and provenance model.
- ContractMesh does not replace the constitution, specification, planning,
  tasking, or implementation workflow of tools such as Spec Kit.

Avoid formulations that claim SDD only manages transient feature specs, or that
SDD does not model persistent constraints. Spec Kit already covers constitutions,
living specs, presets, and related mechanisms.

Prefer not to lean solely on “retrieves what the change must not violate” —
constitution and presets already express non-negotiable rules inside the SDD
process. The sharper claim is grounding via trust, provenance, and source-neutral
retrieval.

## Why the distinction matters

The durable differentiator is **authoring workflow versus independent knowledge
layer**, not “spec versus rule.”

Spec Kit tends to control artifacts created inside its process. ContractMesh can
remain neutral to origin:

- Spec Kit / Kiro / OpenSpec specs
- existing ADRs
- hand-written contracts
- known gaps
- OpenAPI
- tests
- structural graphs
- Git history
- code-derived evidence

Everything may enter; nothing gains authority merely because a popular workflow
created it.

Trust is the separation that matters most. ContractMesh answers:

- Where did this claim come from?
- Was it proposed by an agent or confirmed by a human?
- Did it replace a prior decision?
- What scope does it cover (service vs organization)?
- Does it conflict with a confirmed contract?
- Is it only evidence inferred from the implementation?

Example proposal: “Administrators can permanently delete users” with
`DELETE /users/{id}`.

Before implementation, ContractMesh may already surface:

- a **confirmed contract** that users are never physically removed for audit;
- an **accepted ADR** requiring soft delete and preserved identity IDs;
- a **known risk** that billing still queries deactivated users;
- an **ownership boundary** requiring Platform Security review for identity lifecycle changes.

An SDD plan can be internally consistent and still contradict confirmed knowledge
elsewhere in the workspace. Spec-driven organizes the new intention. ContractMesh
confronts that intention with typed existing decisions, risks, and evidence.

ContractMesh must **not** be positioned as “a place where agents read specs” or
as a competitor to produce the best `spec.md`. Spec Kit, Kiro, and IDEs already
own that authoring surface.

The durable differentiator is:

> ContractMesh determines which knowledge has authority, where it came from,
> what scope it covers, and how it relates to structural evidence.

Organizational knowledge should remain usable by any agent — not owned by
Copilot, Cursor, Kiro, or Spec Kit alone.

## Available today versus planned

### Available today

`preflight_change`, `impact_analysis`, `fetch_hits`, and related tools consult
**existing** confirmed knowledge and repository evidence (contracts, ADRs, known
gaps, owners, tests, structural signals).

They do **not** treat a Spec Kit / Kiro / OpenSpec document as a first-class
indexed artifact. Teams ground an SDD workflow today by running preflight and
retrieval against the durable knowledge already in the workspace.

### Planned (not shipped)

Future work may:

1. **Ingest** feature specs as knowledge with trust level `proposed` (never as
   confirmed authority by default);
2. Add a dedicated **`validate_change_spec`** (name TBD) that takes a change-spec
   artifact and reports conflicts against confirmed contracts, accepted ADRs,
   known risks, ownership boundaries, and evidence;
3. After merge, **suggest** durable promotions (new contracts, ADRs, gaps,
   ownership) for human review.

`proposed` is the reserved trust label for ingested change specs. Do not use
`generated` or `draft` as synonyms for that state — those labels remain for other
artifact classes (for example bootstrap drafts under `.contractmesh/generated/`).

Spec Kit’s extension system could eventually host a preflight-style gate between
plan and tasks/implement. Do **not** promise an official Spec Kit extension or
bundle until one exists.

### Authority warning

> ContractMesh does not make a proposed spec authoritative.
>
> A spec may be indexed as proposed knowledge and checked against confirmed
> contracts, accepted decisions, known risks, and repository evidence.
>
> Promotion into durable engineering knowledge remains an explicit human action.

Post-merge suggestions never auto-promote. Contracts, ADRs, and decisions change
trust level only when a human promotes them.

Illustrative trust mapping (not a shipped ingest matrix):

| Source | Typical trust posture |
|---|---|
| Change `spec.md` | `proposed` |
| Project `constitution.md` | accepted project principle (when ingested) |
| ADR | `confirmed` / `accepted` decision |
| Known gap | `known_risk` |
| OpenAPI / structural graph observation | `inferred` evidence |
| Generated bootstrap note | `generated` / draft |

## Ideal flow together

```text
Spec-driven workflow (e.g. Spec Kit)
  constitution / specify / plan
        │
        ▼
ContractMesh grounding
  │  today: preflight_change / fetch_hits on existing knowledge
  │  planned: validate_change_spec on the proposed spec artifact
  │
  ├── confirmed contracts
  ├── accepted ADRs
  ├── known risks
  ├── owners and boundaries
  ├── cross-repo impact
  └── inferred repository evidence
        │
        ▼
tasks / implement / converge
        │
        ▼
ContractMesh impact / drift review
        │
        ▼
Human reviews promotion suggestions
(durable contracts / ADRs / gaps / ownership only)
```

Useful mental model:

- **spec workspace** — what is being proposed (`proposed` when indexed);
- **confirmed knowledge** — what has already been accepted;
- **evidence layer** — what the repository indicates;
- **promotion** — human action that makes durable knowledge authoritative.

## Related docs

- [Trust model](trust-model.md)
- [Contracts-first design](contracts-first.md)
- [Design principles](design-principles.md)
- [Roadmap](../ROADMAP.md)
