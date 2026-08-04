# Retrieval model

ContractMesh retrieval is designed to be inspectable.

```text
question
-> contract / architecture / integration / known gap
-> related code anchors
-> chunks
-> cited sources
```

## MCP Flow

1. `index_status` checks whether the index exists, is stale or is missing
   chunks.
2. `fetch_hits` is the primary retrieval call. It returns hit metadata, chunk
   text and related anchors.
3. `impact_analysis` gathers contracts, anchors, tests and gaps before a rule
   change.
4. `related_tests` finds tests connected to a behavior query or code symbol.
5. `get_chunk` and `get_doc_chunks` deepen retrieval when a response is
   truncated.
6. `search_docs` is for broad exploration or symbol-only lookup.
7. Direct code reads are reserved for cases where indexed context is not enough.

MCP is only the exposure protocol. The product is the knowledge layer that the
MCP tools expose.

## Why Not Just Vector RAG?

Vector retrieval starts with similarity. ContractMesh starts with intent:
contracts, architecture, ownership boundaries, code anchors, known gaps and
source provenance.

Embeddings can help recall, especially for fuzzy discovery, but they are not a
primary trust signal. The default path should remain deterministic, inspectable,
and explainable.

## Source Provenance

Agent answers should report:

- docs/contracts consulted;
- code anchors surfaced by retrieval;
- direct code reads, if any.

This is the core reliability improvement: the user can audit the path from
question to answer.

## Retrieval regression tests

Retrieval behavior is protected by tests that assert expected top results for
important queries. These tests are intentionally simple because the goal is to
make ranking drift obvious.

Maintainers can run the golden query suite with:

```bash
python3 -m unittest scripts.lib.test_mcp_golden_queries
```

See [Local development](dev-local.md) for the full contributor workflow.
