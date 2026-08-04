# Trust model

ContractMesh separates **facts from inferences**. Contracts, ADRs and known gaps
are explicit engineering knowledge. Graphs, mining, OpenAPI indexes and
embeddings are evidence. Agents should know the difference.

The three high-level classes used in the README map to the typed model as
follows:

- **Explicit** knowledge uses reviewed levels such as `confirmed`, `accepted`,
  and `known_risk`.
- **Generated** bootstrap drafts remain `draft` until a human reviews and
  promotes them (see `.contractmesh/generated/`).
- **Proposed** change specs (planned SDD ingest) use trust level `proposed` —
  not a synonym for `draft` or `generated`. A proposed spec is never
  authoritative until durable knowledge is promoted by a human.
- **Inferred** evidence uses levels such as `implementation`, `inferred`,
  `suggestion`, and `detected_mismatch`.

## Source types and trust levels

| Source | `source_type` | `trust_level` | Agent use |
| --- | --- | --- | --- |
| Contract (`confirmed`) | `contract` | `confirmed` | What **must** hold |
| Contract (`draft`) | `contract` | `draft` | Human proposal — review before acting |
| ADR (`accepted`) | `adr` | `accepted` | Accepted architectural decision |
| Known gap (`Open`) | `known_gap` | `known_risk` | Documented risk |
| Code / test anchor | `code_anchor`, `test_anchor` | `implementation` | Where behavior lives / how it is tested |
| Structural graph | `structural_graph` | `inferred` | Layered evidence (imports, routes, usage) |
| OpenAPI index | `openapi` | `inferred` | HTTP surface |
| Git mining | `git_mining` | `inferred` | Historical suggestion |
| Embedding hit | `embedding` | `suggestion` | Similarity recall only |
| Drift finding | `drift` | `detected_mismatch` | Contract vs implementation mismatch |
| Adapter import | `adapter` | `inferred` | Normalized external graph |
| Feature / change spec (planned) | `change_spec` (planned) | `proposed` | Spec-driven proposal — check against confirmed knowledge; never auto-authoritative |

## Ranking

When sources conflict, prefer higher trust:

```text
confirmed > accepted > known_risk > detected_mismatch > implementation > inferred > suggestion
```

Trusted layers never auto-promote inferred evidence to `confirmed`.

## Precedence rules

1. A `confirmed` contract overrides structural or OpenAPI hints.
2. Drift findings surface alongside gaps; they do not silently rewrite contracts.
3. Bootstrap suggestions and adapter graphs are always `draft` or `inferred`.
4. MCP responses must include `trust_level` in `sources_consulted`.

## Meaning before code

ContractMesh answers **what should be true**, then finds code and evidence:

```text
meaning (contract / ADR / gap)
  → implementation anchors
  → structural graph (optional)
  → drift / evolution (when enabled)
```

This is orchestration, not a generic code-intelligence engine.

See also [design-principles.md](design-principles.md) and [retrieval-model.md](retrieval-model.md).
