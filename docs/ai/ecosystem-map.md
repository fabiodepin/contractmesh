# Ecosystem map

> **Example workspace stub.** Replace this map with your own services and
> contracts after initialization.

High-level dependency map for the workspace. Update this when contracts or
integrations change.

```text
example-app (app)
  -> docs/contracts/APP-CONTRACT-001
  -> src/example.py (ExampleService)

optional web client (web)
  -> calls app HTTP API (when configured)
```

## Flow notes

- Contracts describe stable behavior; ADRs explain architectural boundaries.
- Known gaps link contracts to unresolved validation items.
- Code anchors connect contracts to implementation symbols in each repo.

For cross-boundary changes, use [cross-repo impact](cross-repo-impact.md).
