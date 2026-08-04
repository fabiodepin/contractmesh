# Cross-repo impact checklist

Use this checklist when a change affects more than one repository or contract.

- API routes, payloads, auth headers or error formats.
- Account, organization or workspace scoping.
- Entitlement, billing or feature gating decisions.
- Background jobs, events, webhooks or retry behavior.
- Database migrations and data compatibility.
- Frontend clients that duplicate backend assumptions.
- Known gaps that should be closed, renamed or split.
- Retrieval regression tests that should be updated after intentional behavior changes.

When a change crosses boundaries, review the relevant configured contract files
(typically under `docs/contracts/`) first, then run:

```bash
contractmesh index
contractmesh status
contractmesh check
# Then run the workspace's own test command.
```

Agent answers should finish with the docs, code anchors and direct code files
consulted.
