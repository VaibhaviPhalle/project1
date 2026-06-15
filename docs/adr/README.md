# Architecture Decision Records

Each ADR captures a non-trivial design decision: the context, the alternatives
considered, the choice, and the trade-offs accepted. ADRs are append-only — if
a decision is reversed, write a new ADR that supersedes the old one rather
than editing it.

Format follows a lightweight subset of [MADR](https://adr.github.io/madr/).

## Index

- [0001 — Use LangGraph over plain LangChain for orchestration](./0001-use-langgraph.md)
- [0002 — Tooling: ruff + mypy + pre-commit + uv](./0002-tooling.md)
- [0003 — ChromaDB over Weaviate for local-first deployment](./0003-vector-store-choice.md)
- [0004 — Hybrid retrieval with RRF over weighted score fusion](./0004-rrf-fusion.md)
- [0005 — Section-aware chunking for RFCs over fixed-size chunking](./0005-chunking-strategy.md)
- [0006 — Four-layer citation enforcement](./0006-citation-enforcement.md)
