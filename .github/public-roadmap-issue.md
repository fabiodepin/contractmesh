## Context

ContractMesh `v0.1.x` provides the **installed tool + external workspace** baseline:

- `pipx install "contractmesh[mcp]"` and `contractmesh init --here`
- Local index under `.contractmesh/`, MCP retrieval, code anchors, preflight cards
- `contractmesh bootstrap --suggest` (draft-only foundation)
- Index security: explicit allowlist by default; `index.mode` required; denylist only when deliberately configured
- Trust levels in retrieval ranking (`confirmed` → `accepted` → `known_risk` → `detected_mismatch` → `implementation` → `inferred` → `suggestion`)

This issue tracks strategic direction, not a release-specific task backlog.

See also: [ROADMAP.md](../ROADMAP.md), [RELEASE_NOTES.md](../RELEASE_NOTES.md),
[docs/spec-driven.md](../docs/spec-driven.md).

### Near-term sequence

1. Cold start → drafts humans actually promote
2. Typed provenance on every MCP response
3. Stronger preflight / decision cards
4. Actionable drift (low noise)
5. Thin Spec-driven grounding (`proposed` ingest + `validate_change_spec`)
6. Only then: promotion suggestions, richer evolution, demand-driven adapters

**Strategic differentiator:** typed trust, provenance, source-neutral retrieval.  
**Strongest proof in the wild:** drift vs implementation + proposed change vs confirmed knowledge.

---

## 1. Adoption and onboarding (P0)

**Problem:** the biggest adoption barrier is not navigation — it is the fear of writing a lot of markdown up front.

- [x] Draft-only `contractmesh bootstrap --suggest` baseline
- [x] Guided onboarding (`docs/bootstrap-with-ai.md`, `docs/dev-local.md`)
- [ ] Richer contract, owner, ADR, and known-gap suggestions
- [ ] Continue simplifying first-run prompts and workflows

**Rules (non-negotiable):**

- Bootstrap suggestions are always **draft** artifacts under `.contractmesh/generated/`
- Inferred knowledge is **never** auto-promoted to confirmed contracts

---

## 2. Trust, provenance, and preflight (P0)

- [x] Trust model formalization — schema v3 (`source_type`, `trust_level`), ranking docs
- [x] Structural layer baseline — `imports`, `implements_route`, `uses_service`, `uses_repository`
- [x] Workspace orientation — `orient_workspace()` MCP
- [x] **Allowlist indexing mode** — `index.mode` required; templates/`init` emit allowlist; denylist only when deliberately configured
- [x] Adapter API schema and null adapter
- [x] Baseline `preflight_change` against existing knowledge
- [ ] Complete typed provenance coverage across MCP responses
- [ ] Broader preflight / decision-card evidence (conflicts with confirmed contracts, ADRs, known risks, ownership)

**Non-goals:** a full call graph, universal Tree-sitter parsing, and broad
multi-language semantic analysis in the core.

---

## 3. Drift detection (P1)

Best real-world *proof* of the trust thesis — prioritize actionable, low-noise findings.

- [x] Optional drift index and `list_drift` MCP
- [x] Unresolved-anchor and contract-versus-code findings
- [ ] Lower-noise mismatch classification / stronger validation
- [ ] Harden OpenAPI and client/server mismatch evidence (after OpenAPI is on a real happy path)

---

## 4. Spec-driven grounding (P1 thin slice)

Spec Kit drives the change; ContractMesh grounds it. Spec Kit–style tools may
encode principles and living specs; ContractMesh adds source-neutral trust,
provenance, and retrieval across heterogeneous knowledge. See
[docs/spec-driven.md](../docs/spec-driven.md).

**Near-term:**

- [ ] Ingest change-spec artifacts as trust `proposed` (distinct from bootstrap `draft`)
- [ ] `validate_change_spec`: formal check vs confirmed knowledge (not shipped; no official Spec Kit extension)

**After the thin slice:**

- [ ] Post-merge promotion **suggestions** only; human action required

Do not promise an official Spec Kit extension or compete on authoring `spec.md` / plan / tasks.

---

## 5. Evolution and engineering memory (after grounding)

- [x] Optional evolution graph and git mining
- [x] `evolution_trace` MCP — git links remain `inferred`
- [ ] Enrich contract ↔ ADR ↔ test ↔ change history (after P0/P1 grounding loop)

---

## Parked — reopen only after the grounding loop

- [ ] Structural adapters for external graph providers (see `docs/adapter-api.md`) — schema/no-op enough until demand
- [ ] Optional integrations (e.g. codebase-memory-mcp, fog-context)
- [ ] Embeddings recall (`trust_level: suggestion`) — not the primary product story
- [ ] Session memory via optional adapters

---

## Philosophy

**Facts first. Inference second.**

Confirmed engineering knowledge before inferred repository evidence.

Contracts, ADRs and known gaps are explicit engineering knowledge.

Graphs, mining and embeddings are evidence.

Agents should know the difference — and the provenance of each source.

The trust hierarchy (`confirmed` → `suggestion`) is the core differentiator. Roadmap items must preserve it.

## Non-goals

ContractMesh is not aiming to become a generic code search engine, vector DB, hosted SaaS, autonomous coding agent, Spec Kit / SDD workflow replacement, documentation replacement, competitor in authoring specs/plans/tasks, or near-term official Spec Kit extension.

---

## How to use this issue

- Link PRs and design docs to roadmap items above
- Close sub-items when shipped; update `ROADMAP.md` and `RELEASE_NOTES.md`
- Unchecked items are planned direction, not defects in the current release.
