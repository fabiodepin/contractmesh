# Contracts-first design

Code search and embeddings optimize for finding implementation. ContractMesh
starts with contracts: confirmed decisions, constraints, and known risks.

## Why Contracts First?

Contracts encode behavior, boundaries and ownership better than raw source code.
They answer questions such as:

- What is this service responsible for?
- What is explicitly out of scope?
- Which integration boundaries matter?
- Which known gaps should an agent not miss?

Source code explains implementation. Contracts explain intent.

## Contracts vs ADRs

Contracts describe the expected behavior, ownership boundary and source of
truth for a domain rule. ADRs describe why an architectural decision exists,
which trade-offs were accepted and what should be reviewed before changing the
decision.

An agent should consult both when a change crosses a boundary: the contract says
what must remain true, while the ADR explains why the current shape exists.

## Why Not Embeddings First?

Embeddings are useful for recall, but they are a weak trust signal by
themselves:

- ranking can be opaque;
- architecture is not always in code;
- cross-repo ownership is hard to infer;
- known gaps are usually invisible;
- source provenance is often ad hoc.

ContractMesh may add semantic recall later, but deterministic contracts,
crosslinks and code anchors remain the primary retrieval path.

## Comparison

| Capability | Vector RAG | ContractMesh |
| --- | --- | --- |
| Auditability | Weak | Strong |
| Architectural context | Limited | First-class |
| Cross-repo reasoning | Implicit | Explicit |
| Contracts-aware retrieval | Usually no | Yes |
| Code anchors | Partial | First-class |
| Known gaps | Rare | First-class |
| Deterministic retrieval | Weak | Strong |
| Agent source reporting | Ad hoc | Built into the flow |
