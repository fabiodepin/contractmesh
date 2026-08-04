# Roadmap

ContractMesh evolves across the lifecycle of engineering knowledge:

**Install → Adopt → Understand → Validate → Evolve**

This roadmap describes product direction, not a promise that themes map
one-to-one to release numbers. For shipped changes, see
[RELEASE_NOTES.md](RELEASE_NOTES.md).

Status labels:

- **Available** — implemented in the current `v0.1.x` line.
- **Improving** — usable today, with planned hardening or broader coverage.
- **Planned** — not yet part of the supported public surface.
- **Parked** — intentional deferral; reopen only when the grounding loop is proven.

## Near-term sequence

Force the loop that proves the thesis before expanding surface area:

```text
1. Cold start → drafts humans actually promote
2. Typed provenance visible on every MCP response
3. Stronger preflight / decision cards (conflict with confirmed knowledge)
4. Actionable drift (low noise)
5. Thin Spec-driven grounding: proposed ingest + validate_change_spec
6. Only then: promotion suggestions, richer evolution, demand-driven adapters
```

**Strategic differentiator:** typed trust, provenance, and source-neutral retrieval
across heterogeneous engineering knowledge.

**Strongest proof in the wild:** contracts and decisions that diverge from
implementation (drift) — and proposed changes that conflict with confirmed
knowledge (grounding).

## Foundation — available

- `pipx install "contractmesh[mcp]"` and `contractmesh init --here`
- Index and generated artifacts under `.contractmesh/`
- MCP tools, code anchors, crosslinks, preflight cards
- `contractmesh bootstrap --suggest` (draft-only foundation)
- `tests/fixtures/basic-workspace/` regression fixture (`example-app`)
- `contractmesh check --release` maintainer gate
- **Index security:** explicit allowlist by default for new workspaces;
  `index.mode` required; denylist only when deliberately configured;
  `.contractmeshignore` + engine defaults (see
  [manifest reference](docs/manifest-reference.md))

## 1. Adoption and onboarding — improving (P0)

The biggest adoption barrier today is not navigation — it is the fear of writing
a lot of markdown up front. Without promoted contracts, ADRs, and gaps, Spec Kit
and similar workflows “win by default”: the user writes the change and proceeds.

**Goal:** in about two minutes, a new workspace should have useful drafts that a
human is willing to promote:

- contract drafts
- owner drafts
- ADR drafts
- known-gap drafts

- **Available:** `contractmesh bootstrap --suggest` writes draft output to
  `.contractmesh/generated/bootstrap-suggestions/`.
- **Available:** guided onboarding in `docs/bootstrap-with-ai.md` and
  `docs/dev-local.md`.
- **Improving:** richer owner, contract, ADR, and known-gap suggestions.
- **Improving:** shorter, more guided first-run workflows and prompts.

**Rules:**

- Bootstrap suggestions must always be emitted as draft artifacts.
- Inferred knowledge must never be promoted automatically to confirmed contracts.

## 2. Trust, provenance, and preflight — improving (P0)

- **Available:** trust metadata and ranking (`source_type`, `trust_level`).
- **Available:** optional structural edges for imports, routes, services, and
  repositories.
- **Available:** `orient_workspace` MCP tool for concise workspace orientation.
- **Available:** adapter schema and built-in no-op adapter.
- **Available:** allowlist-first indexing (`index.mode` required; templates use
  allowlist); denylist only when deliberately configured;
  `.contractmeshignore` remains an additional layer;
  `contractmesh index --explain` / MCP `explain_index_path`.
- **Available:** `preflight_change` and related retrieval against existing
  knowledge.
- **Improving:** typed provenance across every MCP response.
- **Improving:** broader preflight and decision-card evidence — surface conflicts
  with confirmed contracts, accepted ADRs, known risks, and ownership before an
  agent writes code (today’s grounding surface; does not wait on Spec-driven
  ingest).

Deep call graphs, universal Tree-sitter parsing, and broad semantic analysis
remain outside the core product scope.

## 3. Drift detection — improving (P1)

Best real-world *proof* of the trust thesis: contracts and decisions that diverge
from implementation. Priority is findings a human or agent will act on — not long
noisy lists.

- **Available:** optional drift index and `list_drift` MCP tool.
- **Available:** unresolved-anchor and contract-versus-code findings.
- **Improving:** lower-noise mismatch classification and stronger validation.
- **Improving (when OpenAPI is on a real happy path):** OpenAPI and
  client/server mismatch evidence.

## 4. Spec-driven grounding — planned (P1 thin slice)

Spec-driven tools (Spec Kit, Kiro, OpenSpec, and similar) drive a change through
specification, planning, and implementation. They may encode constitutions,
living specs, and organizational presets. ContractMesh complements them as an
independent knowledge layer — not a replacement for their workflow.

**Today:** `preflight_change` and retrieval consult existing knowledge and
evidence only.

**Near-term planned (thin slice):**

- ingest feature specs as knowledge with trust level `proposed` (not `draft` /
  `generated`; those remain other artifact classes), with provenance and feature
  scope
- `validate_change_spec` (name TBD): formal check of a change-spec artifact
  against confirmed contracts, accepted ADRs, known risks, and ownership —
  distinct from today’s symbol/diff preflight

**After the thin slice proves value:**

- post-merge **suggestions** to promote durable outcomes (contracts, ADRs, gaps,
  ownership); trust changes only by explicit human action — never auto-promote

A proposed spec is never authoritative until a human promotes durable knowledge.

Do **not** promise an official Spec Kit extension, bundle, or workflow phase until
one exists. Competing on authorship of `spec.md` / plan / tasks is out of scope.

See [docs/spec-driven.md](docs/spec-driven.md).

## 5. Evolution and engineering memory — improving (after grounding)

Useful memory layer; does not close the thesis alone. Enrich after provenance,
preflight, drift noise control, and the Spec-driven thin slice are credible.

- **Available:** optional git mining and evolution links.
- **Available:** `evolution_trace` MCP tool; git evidence remains `inferred`.
- **Improving (later in sequence):** richer contract ↔ ADR ↔ test ↔ change
  history.

## Philosophy

**Facts first. Inference second.**

Confirmed engineering knowledge before inferred repository evidence.

Contracts, ADRs and known gaps are explicit engineering knowledge.

Graphs, mining and embeddings are evidence.

Agents should know the difference — and the provenance of each source.

## Parked — reopen only after the grounding loop

These items stay intentionally deferred so they do not dilute trust/provenance
focus:

- Embeddings recall (`trust_level: suggestion`) — reopen only for recall that
  confirmed retrieval cannot cover; never as the primary product story
- Session memory via optional adapters — agent-memory territory; weak trust
  differentiator
- **Structural adapters** for external graph providers — schema/no-op is enough
  until real demand
- **codebase-memory-mcp** / **fog-context** integrations — premature until the
  core grounding demo is inevitable without them

## Non-goals

ContractMesh does not aim to become:

- a generic code search engine
- a vector database
- a hosted SaaS platform
- an autonomous coding agent
- a replacement for tests or documentation
- a Spec Kit / SDD workflow replacement (Spec Kit, Kiro, and similar remain complementary)
- a competitor in authoring specs, plans, or tasks
- an official Spec Kit extension in the near term (possible later; not promised)

These boundaries protect the trust model: explicit knowledge first, inferred
evidence second, human confirmation always.
