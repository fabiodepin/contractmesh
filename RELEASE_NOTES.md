# ContractMesh Release Notes

## v0.1.6

- **Allowlist-first index security** — `index.mode` is required (`allowlist` or
  `denylist`); no silent default. New workspaces use an explicit allowlist by
  default; denylist is available only when deliberately configured. `init`
  states that only configured paths are analyzed or exposed through MCP.
- **Fail-closed validation** — missing `index.mode` or allowlist with empty
  `include` fails `check` / `index`. Evaluation order: include → exclude →
  `.contractmeshignore` → engine defaults. Repo-scoped patterns: `repo_name:glob`.
- **IndexPolicy** — single gate for search index, code anchors, structural
  graph, OpenAPI discovery, and doc validation (with directory pruning).
- **Explainability** — `contractmesh index --explain PATH`,
  `contractmesh index --show-policy`, MCP `explain_index_path`, and
  `index_policy` stats on index summary / `index_status`.

## v0.1.5

- **Deprecation metadata** — `docs_drift_check` returns `deprecated`,
  `replacement=documentation_impact`, `replacement_cli`; CLI `docs drift`
  warns on stderr.
- **Reason provenance** — optional `source.{repo,path,symbol,line}` on evidence.
- **`confirmation_kind`** — `structural` | `semantic` under public `state=confirmed`.
- **`core_documentation_impact()`** — contract helper so engine/CLI/MCP/preflight/
  `pr_impact` can assert identical core fields.

## v0.1.4

- **`documentation_impact`** — evidence-based docs review model (`none` /
  `possible` / `confirmed`) with typed evidence kinds, separate `confidence`
  and `enforcement`. Consumed by `preflight_change`, `pr_impact`, CLI
  `docs impact [--diff]`, and MCP `documentation_impact`.
- **`docs_drift_check`** kept as a deprecated alias of the same analysis.
- Confirmed state is never raised solely because code changed and a linked
  doc did not.

## v0.1.3

- **Related-anchor ranking** — prefer front-matter `related_anchors` and
  behavioral types (controller/service/page) over entities in `fetch_hits`.
- **Impact density** — cap/rank code anchors (soft caps for entity/multitenancy).
- **Primary-symbol tests** — `related_tests` / preflight require the target
  symbol when provided (drops tangential tests).
- **Honest index status** — `embedding_status=disabled` when embeddings are off;
  OpenAPI/embeddings hints; discover common OpenAPI filenames while indexing.

## v0.1.2

- **`impact_analysis` noise reduction** — soft IDF on query tokens, relative
  seed-score cutoff, expand `related_contracts` only from the strongest seed
  contract, keep `known_gaps` as dedicated gap docs (not every contract with
  gap IDs), and raise the bar for token-only test matches.
- Regression coverage in `scripts/lib/test_impact_analysis_noise.py`.

## v0.1.1

- Cross-repo fallback when linking contract/ADR symbols to code anchors (monorepo
  docs at workspace root → symbols in child repos)
- Java class extractor accepts modifiers such as `final` / `sealed`
- Broader Java path hints (`/service/` singular, util/entity/support types)
- Gap ID extraction no longer treats `*-CONTRACT-*` ids as known gaps
- Frontend drift check receives repo list and looks for common HTTP client module names
- TypeScript anchors for `*Page` / `*Store` and common `api-client` / `http` modules
- Pin MCP extra to `mcp>=1.2.0,<2` (mcp 2.x removed `mcp.server.fastmcp` / FastMCP)

## v0.1.0

First public release of ContractMesh as an **installed tool** with **external
workspaces**.

### What changed

ContractMesh is no longer a repository you clone to host your projects inside.
Install the CLI and run it in any existing project:

```bash
pipx install "contractmesh[mcp]"
cd ~/projects/my-project
contractmesh init --here
contractmesh index
contractmesh status
contractmesh check
contractmesh mcp
```

### Highlights

- **Installed CLI** — `pipx install "contractmesh[mcp]"` (MCP extra required for `contractmesh mcp`)
- **External workspace** — `contractmesh init --here` in your real project
- **Layout** — index and generated artifacts under `.contractmesh/`
- **Commands** — `init`, `index`, `status`, `check`, `graph`, `mcp`, `doctor`,
  `bootstrap --suggest`, `self check`
- **`contractmesh.yml`** — single workspace manifest (no `scripts/repos.conf`)
- **MCP server** — `fetch_hits`, `impact_analysis`, `index_status`,
  `related_tests`, `preflight_change`, and more
- **Code anchors** — Java, TypeScript, Go, Python, YAML
- **Test anchors** — common test locations
- **Trust** — bootstrap suggestions are draft-only; humans confirm contracts
- **Regression tests** — `tests/fixtures/basic-workspace/` with `example-app`
- **Release gate** — `contractmesh check --release` (maintainer/CI smoke in source checkout only)

### Removed from v0.1 public surface

- Bundled demo workspace inside the tool repository
- `contractmesh demo` command
- `scripts/repos.conf` manifest fallback
- `docs/generated/` runtime layout (replaced by `.contractmesh/`)

### Limitations

v0.1.0 does not include vector databases, hosted UI, SaaS, or autonomous agent
behavior. Embeddings remain optional and off by default. The local index is the
context boundary for MCP clients — use `.contractmeshignore` for secrets and
sensitive paths.
