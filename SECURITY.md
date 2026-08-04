# Security policy

ContractMesh indexes local repositories and can expose retrieved snippets,
contracts, code anchors, and generated metadata through MCP tools.

Generated indexes should be treated as derived source material and may contain
sensitive information extracted from the indexed workspace.

## Supported versions

Only the latest released version receives security fixes.

## Reporting a vulnerability

Please open a private report through
[GitHub Security Advisories](https://github.com/fabiodepin/contractmesh/security/advisories/new).

Please do not disclose vulnerabilities publicly before a fix is available.

## Security model

ContractMesh is designed as a local-first tool:

- repositories are indexed locally;
- MCP communication uses local stdio by default;
- no cloud services or telemetry are required;
- generated indexes stay inside the workspace unless explicitly shared.

ContractMesh does not transmit workspace contents outside the local environment
unless external tools, agents, or integrations are configured by the user.

## Guidance for users

- Do not publish `.contractmesh/index/` from private workspaces.
- Review `contractmesh.yml` before running index builds.
- ContractMesh supports allowlist and denylist indexing policies. New workspaces
  use an explicit allowlist by default; denylist is available only when
  deliberately configured.
- A workspace without an explicit `index.mode` is invalid. In allowlist mode, at
  least one `include` rule is required — ContractMesh fails closed instead of
  falling back to broader indexing.
- Review `index.include` / `index.exclude` and `.contractmeshignore` before
  indexing (see [docs/manifest-reference.md](docs/manifest-reference.md)).
- Debug with `contractmesh index --explain PATH` or `--show-policy`.
- Keep `.contractmesh/mcp/` and `.cursor/mcp.json` untracked because they may
  contain local absolute paths.
- Sanitize example repositories before sharing screenshots or demos.
- Review MCP client permissions before connecting external agents to private
  workspaces.

## Scope limitations

ContractMesh improves retrieval quality and provenance but does not replace:

- source code review;
- access controls;
- secret management;
- dependency scanning;
- application security testing.

Users remain responsible for deciding which repositories and documents are made
available to AI agents.