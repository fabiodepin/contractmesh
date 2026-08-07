# Workspace manifest reference

`contractmesh.yml` is the workspace manifest. It lives at the root of each
**external** project workspace (created by `contractmesh init --here`), not inside
the ContractMesh tool repository.

Status labels in this document:

- **Active** — implemented in the current release
- **Planned** — documented direction; not enforced yet

## Minimal example

```yaml
name: example-app
mode: basic
workspace_mapping_version: v3
repos:
  - path: .
    name: app
docs:
  contracts:
    - docs/contracts
  adrs:
    - docs/adrs
  gaps:
    - docs/known-gaps.md
lint:
  require_owner: true
  require_ids: true
  require_valid_crosslinks: true
index:
  mode: allowlist
  include:
    - src/**
    - tests/**
    - docs/**
    - README.md
```

## Top-level fields

| Field | Status | Description |
| --- | --- | --- |
| `name` | Active | Workspace display name |
| `mode` | Active | Template mode (`basic`, `monorepo`, …) |
| `workspace_mapping_version` | Active | Manifest schema version |
| `repos` | Active | Indexed repositories (`path`, `name`) |
| `docs` | Active | Contract, ADR, and known-gap doc roots |
| `lint` | Active | Doc governance checks |
| `index` | Active | Index feature flags (see below) |
| `preflight` | Active | Preflight card thresholds (optional) |

## `repos`

Each entry maps a repository path relative to the workspace root:

```yaml
repos:
  - path: services/billing-api
    name: billing-api
  - path: .
    name: app
```

The indexer reads docs and code anchors from each listed repository.

## `docs`

```yaml
docs:
  contracts:
    - docs/contracts
  adrs:
    - docs/adrs
  gaps:
    - docs/known-gaps.md
```

Paths are relative to each repo root unless the repo path is `.`.

## `lint`

```yaml
lint:
  require_owner: true
  require_ids: true
  require_valid_crosslinks: true
```

Used by `contractmesh check` and maintainer doc lint scripts.

## `index` feature flags

```yaml
index:
  mode: allowlist   # required — no silent default
  include:
    - src/**
    - tests/**
    - docs/**
    - README.md
  structural_graph: false
  git_mining: false
  embeddings: false
  openapi: false
  drift: false
  adapters: []
  # Max code/test anchors kept per repo (default 500). Excess is dropped after
  # sorting by anchor_type priority (controllers/services first), then weight.
  code_anchor_cap_per_repo: 500
  # Optional overrides for large repos (list form works with the YAML subset parser).
  code_anchor_cap_by_repo:
    - billing-api=1200
```

Boolean feature flags default to `false`. **`index.mode` is required** and has no
silent fallback.

`code_anchor_cap_per_repo` defaults to `500`. Raise it for large monorepos (e.g. `850`)
when curated collectors still exceed the cap. Truncation prefers high-signal
`anchor_type` values and higher document `weight`, not discovery order.

`code_anchor_cap_by_repo` overrides the default for named repos. Prefer this over raising
the global cap when only one or two repositories are outliers. Use `repo=N` list
entries (compatible with the built-in YAML subset) or a mapping if your loader
supports nested maps.

Curated Vue SFCs (`vue_component`) are indexed from `src/views/*.vue`,
`src/system/components/**/*.vue`, and `src/global/components/**/*.vue` (PascalCase
filenames only).

Java code anchors also include curated persistence layers (`/repository/`,
`/jooq/`, `/mapper/`, `/specification/`) in addition to controllers/services.
TypeScript also indexes `src/system/types/**` and `src/global/types/**` as
`ts_type` (exported `type` / `interface` symbols), plus common Node/Express
patterns (`*-router.ts`, `*-repository.ts`, `*-middleware.ts`, `*-factory.ts`,
`config.ts`, and one-level `src/<module>/index.ts` barrels).

## Index security model

ContractMesh supports allowlist and denylist indexing policies.

New workspaces use an explicit allowlist by default. Denylist mode is available
only when deliberately configured.

### Allowlist — default for new workspaces

Templates and `contractmesh init` emit allowlist manifests with an explicit
`include` list.

```yaml
index:
  mode: allowlist
  include:
    - src/**
    - tests/**
    - docs/**
    - README.md
  exclude:
    - secrets/**
```

That starter list is intentional for a generic template. Unconventional layout
roots are **not** indexed automatically — for example `app/`, `lib/`,
`packages/`, `services/`, `cmd/`, and `internal/`. Add them to `include` when
they contain code or docs you want ContractMesh to analyze.

Use `contractmesh index --show-policy`, `contractmesh index --explain PATH`, or
`contractmesh status` after the first index to confirm what is in scope.

`--explain` reports two layers:

1. **IndexPolicy** — whether ContractMesh may read the path (`allowed`)
2. **Collectors** — whether that path becomes a markdown doc or code/test
   anchor (`indexed_as` / `why_not_indexed`)

Allowlisting a path does not automatically create a search document. Config
files, Prisma SQL, and most TypeScript sources are security/review boundaries
unless a collector indexes them.

### Include pattern semantics

| Pattern | Meaning |
| --- | --- |
| `package.json` | Workspace-root file only |
| `/package.json` | Same (explicit root form) |
| `**/package.json` | Any depth |
| `*.pem` | Any path segment (wildcard basenames) |
| `server/src/` | Directory and everything under it |

Bare exact names in `index.include` / `index.exclude` are **root-relative** for
security clarity. Use `**/name` when any depth is intended.

Monorepo example (repo-scoped globs are relative to that repo path):

```yaml
index:
  mode: allowlist
  include:
    - docs/**
    - README.md
    - billing-api:src/**
    - billing-api:tests/**
    - admin-web:src/**
```

### Denylist — only when deliberately configured

Denylist indexes everything in scope except matches of `index.exclude`,
`.contractmeshignore`, and engine defaults. Configure it only deliberately:

```yaml
index:
  mode: denylist
```

| Field | Status | Description |
| --- | --- | --- |
| `index.mode` | Active | **Required.** `allowlist` or `denylist` — no silent default |
| `index.include` | Active | Required and non-empty when `mode: allowlist` |
| `index.exclude` | Active | Extra paths removed after include (both modes) |

`.contractmeshignore` remains an extra denylist layer on top of manifest rules.

**Fail-closed:**

- A workspace without an explicit `index.mode` is invalid.
- In allowlist mode, at least one `include` rule is required.
- ContractMesh fails closed instead of falling back to broader indexing.

Evaluation order:

```text
repos + docs roots (manifest)
→ include globs (allowlist mode only)
→ exclude globs (manifest)
→ .contractmeshignore
→ DEFAULT_IGNORE_PATTERNS (engine baseline)
```

Paths are workspace-relative unless written as `repo_name:glob` (repo-relative).
Globs support `*`, `?`, `**`, and trailing `/` for directories.

Debug:

```bash
contractmesh index --show-policy
contractmesh index --explain src/example.py
```

MCP: `explain_index_path`, and `index_status` includes `index_policy`.

## `preflight` (optional)

```yaml
preflight:
  high_min_score: 6
  medium_min_score: 3
  soft_block_enabled: true
  soft_block_require:
    - HIGH
```

Controls `preflight_change` risk scoring and soft-block policy. See
`contractmesh.yml` in the tool repo tests or templates for defaults.

## Related docs

- [Security and privacy](security-privacy.md) — index boundary, allowlist default, denylist deliberate
- [Workspace conventions](ai/workspace-conventions.md)
- [Roadmap](../ROADMAP.md) — trust and indexing direction
