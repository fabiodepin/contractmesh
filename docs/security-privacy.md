# Security and privacy

ContractMesh is designed as a local-first knowledge layer for AI agents.
The default MCP server exposes retrieval context over local stdio. It does not
push data to a hosted service and it does not provide code-editing tools.

## Default model

- **Local-first:** indexing and MCP retrieval run on your machine or CI runner.
- **Read-only by default:** MCP tools expose context, provenance, impact analysis
  and related tests.
- **No cloud requirement:** ContractMesh does not require a hosted backend, vector
  database or SaaS account.
- **No code changes:** the MCP server does not execute edits, migrations, shell
  commands or autonomous coding actions.

## Common questions

**Does ContractMesh send my code somewhere?**

No. Indexing and MCP run locally. Nothing is uploaded to ContractMesh infrastructure.

**Can it index secrets?**

Only if they are not excluded. The index is the security boundary: anything indexed
may be surfaced to an MCP client. Use `.contractmeshignore` and review
`contractmesh index` output before connecting agents in production workspaces.

## What agents can see

An agent connected through MCP can see the documents, chunks, metadata, code
anchors and test anchors present in the ContractMesh index.

Review what you index before connecting an agent, especially when contracts, ADRs
or architecture docs contain internal customer names, private endpoints, incident
history, credentials or sensitive business rules.

## Use .contractmeshignore

Use [.contractmeshignore](../.contractmeshignore) as a **denylist** layer on top
of the workspace manifest. The matcher is gitignore-like and supports exact,
glob and directory patterns.

Default exclusions (always applied, even without a workspace file) include:

| Category | Examples |
| --- | --- |
| Secrets | `.env`, `.env.*`, `*.pem`, `*.key`, `secrets/` |
| Cloud | `.aws/`, `.azure/`, `.gcp/`, `*.tfvars`, `terraform.tfstate*` |
| SSH | `.ssh/`, `id_rsa`, `id_ed25519` |
| Package auth | `.npmrc`, `.pypirc`, `pip.conf` |
| Build output | `node_modules/`, `target/`, `.venv/`, `dist/` |
| ContractMesh | `.contractmesh/index/`, `.contractmesh/generated/` |

Ship the template from `contractmesh init --here` and add project-specific paths
when sensitive data lives in custom locations.

## Index security policies

ContractMesh supports allowlist and denylist indexing policies.

New workspaces use an explicit allowlist by default. Denylist mode is available
only when deliberately configured.

A workspace without an explicit `index.mode` is invalid.

In allowlist mode, at least one `include` rule is required. ContractMesh fails
closed instead of falling back to broader indexing.

Optional `index.exclude` applies in both modes. `.contractmeshignore` remains an
extra denylist layer on top.

Full schema, semantics, and evaluation order are documented in the
[manifest reference](manifest-reference.md#index-security-model).

```bash
contractmesh index --show-policy
contractmesh index --explain path/to/file
```

## Private repositories

ContractMesh can index private repositories because it runs locally, but the
same caution applies: anything indexed may be surfaced to an MCP client and may
appear in agent logs or chat transcripts depending on the client.

Before sharing logs externally, review:

- retrieved chunks;
- source paths;
- contract and ADR content;
- known gaps;
- agent transcripts that include MCP output.

## Current limitations

- `.contractmeshignore` and allowlist globs are intentionally simple and are not
  a complete reimplementation of Git's ignore engine.
- New workspaces use an explicit allowlist by default; denylist is available only
  when deliberately configured.
- The default indexer does not perform secret scanning.
- Generated `.contractmesh/` files are ignored by Git by default, but local
  files still exist on disk until removed.
- MCP access control is delegated to the local MCP client configuration.
- ContractMesh does not redact sensitive text from documents that were already
  indexed.

## Related docs

- [README](../README.md)
- [Manifest reference](manifest-reference.md)
- [MCP client setup](mcp-clients.md)
- [Roadmap](../ROADMAP.md)
