# ContractMesh

> **Facts first. Inference second.**

[![Tests](https://github.com/fabiodepin/contractmesh/actions/workflows/checks.yml/badge.svg)](https://github.com/fabiodepin/contractmesh/actions/workflows/checks.yml)
[![PyPI](https://img.shields.io/pypi/v/contractmesh)](https://pypi.org/project/contractmesh/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
![Local-first](https://img.shields.io/badge/local--first-yes-green.svg)
![MCP compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)

ContractMesh is a **trust-aware engineering knowledge layer for AI agents**.

Code search helps agents find implementation.
ContractMesh helps them retrieve what engineers have decided must remain true:
behavioral contracts, architecture decisions, ownership boundaries, known gaps,
compatibility constraints, and related repository evidence.

It preserves the distinction between:

- confirmed engineering knowledge;
- accepted decisions and known risks;
- generated suggestions awaiting review;
- evidence inferred from code, graphs, OpenAPI, Git, and structural analysis.

ContractMesh runs locally, exposes retrieval through MCP, and applies an explicit
fail-closed indexing policy across the workspace.

It is not another code indexer, vector database, autonomous agent, or hosted
knowledge portal.

It is the engineering knowledge layer agents consult before they change the code.

**Local-first. MCP-native. Allowlist-first.**

Your real `payment-service`, `my-app`, or any other repository stays where it is.
You do not copy or clone your source code into the ContractMesh repository.

---

## Why ContractMesh?

Code search retrieves implementation. ContractMesh retrieves decisions,
constraints, known risks, and the evidence connected to them.

Most AI development workflows retrieve code and ask the agent to infer everything
else. ContractMesh retrieves both **confirmed engineering knowledge** and
**inferred repository evidence**, while preserving the distinction between them.

| Explicit engineering knowledge | Inferred repository evidence |
|---|---|
| Contracts | Structural graph |
| Architecture Decision Records | Code relationships |
| Known gaps | OpenAPI / Git mining |
| Human-reviewed decisions | Embeddings (optional) |

Functional rule: **confirmed engineering knowledge before inferred repository evidence.**

Agents may retrieve both, but they should never confuse one with the other.

ContractMesh delivers the most value when teams make engineering decisions,
constraints, ownership, and known risks explicit.

Bootstrap can help discover and draft missing knowledge, but it does not replace
human engineering judgment.

### How it complements other tools

| Category | What it optimizes | Role of ContractMesh |
|---|---|---|
| Code search and RAG | Finding relevant implementation | Adds explicit decisions, limits, and risks |
| Agent memory | Persisting and recalling context | Adds trust, provenance, and human promotion |
| Spec-driven development (Spec Kit, Kiro, OpenSpec) | Driving a change through spec → plan → tasks | Independent trust/provenance layer across heterogeneous knowledge |
| Portals and documentation | Organizing knowledge for people | Makes that knowledge retrievable by agents at runtime |
| API contracts and tests | Validating executable interfaces | Records intent, compatibility, and limits tests do not explain |
| Graphs and impact analysis | Inferring structural relationships | Treats those relationships as evidence, not organizational truth |

Agent memory typically optimizes persistence and recall. ContractMesh additionally
models provenance, trust, promotion, and the distinction between confirmed
knowledge and inferred evidence.

### Spec-driven development

> **Spec Kit drives the change. ContractMesh grounds the change.**

Spec Kit–style tools structure how a proposed change becomes an implementation
(constitution, spec, plan, tasks, converge). ContractMesh provides an
independent trust and provenance layer: confirmed decisions, constraints, known
risks, ownership boundaries, and repository evidence — regardless of which tool
created the spec.

Specs describe the proposed change. ContractMesh grounds it in existing
engineering knowledge and evidence.

A plan that passes checks inside one SDD workflow can still contradict confirmed
contracts, ADRs, or known risks elsewhere in the workspace.

**Today:** `preflight_change` and retrieval consult existing knowledge and
evidence. Spec Kit / Kiro / OpenSpec files are not yet first-class indexed
artifacts.

**Planned:** ingest change specs as `proposed`, `validate_change_spec` against
confirmed knowledge, post-merge promotion suggestions — never auto-promote.

ContractMesh does not replace Spec Kit’s constitution, planning, or tasking
workflow. It is not a feature-spec manager.

See [Spec-driven development and ContractMesh](docs/spec-driven.md).

---

## Philosophy

> **Facts first. Inference second.**

Humans define confirmed engineering knowledge.

AI may propose drafts and discover evidence.

ContractMesh preserves the distinction — and the provenance — across retrieval.

---

## Install

ContractMesh requires **Python 3.10 or newer**.

The recommended installation method is [`pipx`](https://pipx.pypa.io/), which installs the CLI in an isolated environment:

```bash
pipx install "contractmesh[mcp]"
```

The `mcp` extra installs the runtime required to:

- start the ContractMesh MCP server with `contractmesh mcp`;
- validate MCP support with `contractmesh self check`.

Verify the installation:

```bash
contractmesh --help
contractmesh self check
```

For an editable source installation, see [Develop ContractMesh](#develop-contractmesh).

---

## Use in your project

ContractMesh is initialized **inside the project that you want agents to understand**.

For example:

```bash
cd ~/projects/my-project
contractmesh init --here
```

`init --here` creates the ContractMesh workspace structure in the current
project: manifest, ignore files, empty knowledge directories, and `.gitignore`
updates. It does **not** add example code, tests, or demo contracts unless you
pass `--with-examples`.

In existing projects it also:

- sets `name` from the directory name (not `example-app`);
- reuses existing knowledge paths when found (for example `docs/adr`);
- prints candidate allowlist roots that are present but not yet included —
  without authorizing them automatically.

It does not move or copy your source code.

### 1. Initialize the workspace

```bash
contractmesh init --here
```

Use this once for each project. In an existing repository the default is
brownfield-safe (config + empty knowledge locations only).

For a local smoke scaffold with demo contracts and sample code:

```bash
contractmesh init --here --with-examples
```

The generated `contractmesh.yml` manifest defines what belongs to the workspace and what ContractMesh may index.

ContractMesh supports allowlist and denylist indexing policies.

New workspaces use an explicit allowlist by default. Denylist mode is available
only when deliberately configured.

A workspace without an explicit `index.mode` is invalid. In allowlist mode, at
least one `include` rule is required — ContractMesh fails closed instead of
falling back to broader indexing.

Review `contractmesh.yml` before indexing. Only the configured paths will be
analyzed or exposed through MCP. See the
[manifest reference](docs/manifest-reference.md).

### 2. Optionally generate knowledge drafts

```bash
contractmesh bootstrap --suggest
```

This step is optional.

It analyzes available project material and writes suggested knowledge into:

```text
.contractmesh/generated/bootstrap-suggestions/
```

Generated suggestions are **drafts**, not trusted engineering facts.

ContractMesh does not automatically promote them into canonical documentation. A human must review and move accepted content into locations such as:

```text
docs/contracts/
docs/adrs/
docs/known-gaps.md
```

You can skip bootstrap entirely and write the explicit knowledge manually.

### 3. Build the local index

```bash
contractmesh index
```

This indexes only paths allowed by the workspace policy (`index.mode` + `include` /
`exclude`) and `.contractmeshignore`, then builds the local retrieval index.

```bash
contractmesh index --show-policy
contractmesh index --explain src/example.py
```

The generated index is stored under:

```text
.contractmesh/index/
```

The index is local and should remain gitignored.

Run `contractmesh index` again after relevant source code or engineering documentation changes.

### 4. Inspect workspace status

```bash
contractmesh status
```

This reports the current state of the ContractMesh workspace and index.

Use it to confirm that the project was initialized and that indexed knowledge is available before connecting an agent.

### 5. Validate the workspace

```bash
contractmesh check
```

This validates the current project workspace.

It is intended to identify invalid configuration, missing required structures, and other conditions that could make retrieval unreliable.

Run it locally and in project CI when appropriate.

### 6. Start the MCP server

```bash
contractmesh mcp
```

This starts the ContractMesh MCP server for the current workspace.

The command remains running while an MCP client communicates with it. Configure Cursor, Claude Code, Gemini CLI, or another MCP-compatible client to launch this command from the project directory.

See [MCP client setup](docs/mcp-clients.md) for client-specific configuration.

### Typical workflow

After the first setup, the normal flow is:

```bash
cd ~/projects/my-project

contractmesh index
contractmesh status
contractmesh check
contractmesh mcp
```

`bootstrap --suggest` is not required on every run. Use it when you want ContractMesh to propose new knowledge drafts for human review.

---

## Quick smoke test

The following commands create a temporary example workspace without requiring an existing repository:

```bash
mkdir example-test
cd example-test

contractmesh init --here --template basic --with-examples
contractmesh index
contractmesh status
contractmesh check
```

This verifies that ContractMesh can initialize, index, inspect, and validate a basic workspace.

The smoke test does not start the MCP server. Run the following separately when you want to test an MCP client connection:

```bash
contractmesh mcp
```

---

## Example

Suppose an agent is asked:

> Can I safely remove this field?

Without explicit engineering knowledge, the agent may search references in the codebase and conclude that the field appears unused.

That conclusion may ignore external consumers, compatibility guarantees, incomplete migrations, or decisions that are not visible in the implementation.

With ContractMesh, the agent may retrieve:

```text
Contract
  External API consumers depend on this field.

ADR-014
  Compatibility must be preserved until v3.

Known gap
  The consumer migration has not been completed.

Related tests
  tests/api/compatibility/
```

The agent can now reason from documented engineering facts and supporting repository evidence instead of relying only on code-level assumptions.

---

## Trust model

ContractMesh can suggest knowledge, but only humans can confirm it.

| Knowledge class | Meaning |
|---|---|
| Explicit | Written or reviewed by humans and stored in a canonical knowledge location |
| Generated | Proposed by AI or automation and awaiting human review |
| Inferred | Derived from repository structure, search, graphs, embeddings, or mining |

The location of an artifact matters.

For example:

```text
.contractmesh/generated/
```

contains untrusted drafts, while reviewed contracts belong in:

```text
docs/contracts/
```

The promotion from generated draft to explicit engineering knowledge is a deliberate human action.

See:

- [Trust model](docs/trust-model.md)
- [Bootstrap with AI](docs/bootstrap-with-ai.md)

---

## Security and privacy

ContractMesh is **local-first**.

It does not require a cloud backend and does not upload your repository or index to a ContractMesh-hosted service.

Indexing is controlled by:

- `contractmesh.yml`;
- `.contractmeshignore`.

Default exclusions should cover common sensitive or irrelevant material such as secrets, cloud credentials, SSH keys, Terraform state, dependency directories, and build artifacts.

You remain responsible for reviewing the effective workspace scope.

### The index is the MCP security boundary

If a file is indexed, an authorized MCP client may be able to retrieve information from it.

Do not index files that should not be exposed to the agents using the workspace.

Before using ContractMesh in a sensitive repository:

1. review `contractmesh.yml`;
2. review `.contractmeshignore`;
3. build the index;
4. inspect the resulting workspace status;
5. validate the workspace with `contractmesh check`.

See [Security and privacy](docs/security-privacy.md) for the complete security model and enterprise guidance.

---

## Workspace layout

| Path | Purpose | Commit to Git? |
|---|---|---|
| `contractmesh.yml` | Workspace manifest and indexing scope | Yes |
| `.contractmeshignore` | Extra paths excluded from indexing | Yes |
| `index.mode` / `include` / `exclude` | Required index security policy (explicit allowlist by default) | Yes |
| `docs/contracts/` | Explicit engineering contracts | Yes |
| `docs/adrs/` | Architecture Decision Records | Yes |
| `docs/known-gaps.md` | Known limitations, debt, and incomplete work | Yes |
| `.contractmesh/index/` | Generated local retrieval index | No |
| `.contractmesh/generated/` | Generated drafts awaiting review | Usually no |
| `.contractmesh/mcp/` | Generated or local MCP configuration | Depends on configuration |

Canonical engineering knowledge should remain reviewable through the normal Git workflow.

Generated indexes and machine-local artifacts should remain outside version control.

---

## MCP tools

ContractMesh can be used by Cursor, Claude Code, Gemini CLI, and other MCP-compatible clients.

Core tools include:

| Tool | Purpose |
|---|---|
| `fetch_hits` | Retrieve relevant explicit knowledge and repository evidence |
| `impact_analysis` | Identify contracts, components, and knowledge related to a proposed change |
| `related_tests` | Find tests associated with retrieved knowledge or affected areas |
| `index_status` | Inspect index availability and workspace health |
| `preflight_change` | Review contracts, gaps, tests, and risk before editing a symbol |
| `pr_impact` | Map a branch or pull-request diff to affected knowledge and tests |
| `documentation_impact` | Identify evidence-based documentation review targets |

The MCP client does not need direct knowledge of ContractMesh's internal index format. It interacts with the tools exposed by the local server.

See [MCP client setup](docs/mcp-clients.md) for configuration examples and the
complete tool surface, including optional flag-gated tools.

---

## Command reference

| Command | Run from | Purpose |
|---|---|---|
| `contractmesh init --here` | Project root | Initialize config + empty knowledge dirs (no demo content) |
| `contractmesh init --here --with-examples` | Empty/demo dir | Also copy scaffold example code, tests, and demo contracts |
| `contractmesh bootstrap --suggest` | Initialized project | Generate untrusted knowledge drafts for review |
| `contractmesh index` | Initialized project | Build or refresh the local retrieval index |
| `contractmesh status` | Initialized project | Inspect workspace and index state |
| `contractmesh check` | Initialized project | Validate workspace configuration and knowledge structure |
| `contractmesh graph` | Initialized project | Export the indexed knowledge graph as JSON |
| `contractmesh mcp` | Initialized project | Start the MCP server for that workspace |
| `contractmesh doctor` | Any directory | Diagnose installation and workspace setup |
| `contractmesh self check` | Any directory | Validate the installed ContractMesh package and optional MCP runtime |
| `contractmesh check --release` | ContractMesh source checkout | Run maintainer and release validation |

For the full CLI syntax:

```bash
contractmesh --help
contractmesh <command> --help
```

Examples:

```bash
contractmesh init --help
contractmesh bootstrap --help
contractmesh index --help
```

---

## Learn more

- [Architecture](docs/architecture.md)
- [Documentation index](docs/README.md)
- [Trust model](docs/trust-model.md)
- [Spec-driven development](docs/spec-driven.md)
- [Bootstrap with AI](docs/bootstrap-with-ai.md)
- [Manifest reference](docs/manifest-reference.md)
- [Retrieval model](docs/retrieval-model.md)
- [MCP client setup](docs/mcp-clients.md)
- [Security and privacy](docs/security-privacy.md)
- [Contributing](CONTRIBUTING.md)
- [Roadmap](ROADMAP.md)
- [Release notes](RELEASE_NOTES.md)

---

## Develop ContractMesh

Clone the ContractMesh source repository:

```bash
git clone https://github.com/fabiodepin/contractmesh.git
cd contractmesh
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the project in editable mode with MCP support:

```bash
python -m pip install -e ".[mcp]"
```

Validate the source installation:

```bash
contractmesh self check
```

Run a targeted unit test while developing:

```bash
python3 -m unittest scripts.lib.test_fetch_hits
```

See [Contributing](CONTRIBUTING.md) for the development workflow and use the
release validation command below for the complete maintained check set.

### Release validation

The following command is intended only for maintainers and CI operating from a ContractMesh source checkout:

```bash
contractmesh check --release
```

It is not a replacement for `contractmesh check` and is not intended for ordinary project workspaces or isolated `pipx` installations.

| Command | Scope |
|---|---|
| `contractmesh self check` | Installed ContractMesh package and MCP dependencies |
| `contractmesh check` | The user's current ContractMesh workspace |
| `contractmesh check --release` | ContractMesh source tree and release requirements |

---

## Roadmap

ContractMesh evolves from a local explicit-knowledge foundation toward stronger trust, structural analysis, drift detection, and knowledge evolution.

Current roadmap themes:

- **Foundation:** maintain a reliable CLI, workspace model, local index, retrieval, and MCP baseline;
- **Adoption:** help teams discover and draft missing engineering knowledge;
- **Trust and structure:** strengthen governance, provenance, structural evidence, and indexing boundaries;
- **Drift and evolution:** identify divergence between implementation and explicit knowledge;
- **Advanced retrieval:** improve impact analysis and knowledge-aware agent workflows.

The roadmap marks each capability as available, improving, or planned. Themes do
not map one-to-one to release numbers.

See [ROADMAP.md](ROADMAP.md) for the current scope and release status.

---

## License

ContractMesh is available under the Apache License 2.0.

See [LICENSE](LICENSE).