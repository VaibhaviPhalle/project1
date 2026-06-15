# ADR 0003 — Vector store: ChromaDB over Weaviate (local-first)

- **Status:** Proposed (finalized in Step 4)
- **Date:** 2026-06-14

## Context

The project must run locally on commodity hardware with zero infrastructure
cost. Production-grade vector stores (Weaviate, Qdrant, pgvector) all add
operational overhead (Docker, persistent volumes, separate process).

## Decision (preliminary)

Use **ChromaDB** in `PersistentClient` mode — runs in-process, persists to a
local directory, no Docker required. One collection per corpus version
(`auth_corpus_v1`).

## Alternatives considered

1. **Weaviate** — feature-rich but requires a separate server.
2. **Qdrant** — fast, but again requires a server for persistence.
3. **FAISS** — embeddings only, no metadata store. Would need a sidecar.
4. **pgvector** — production-grade but requires Postgres.

## Consequences

- (+) Zero-config local dev; `pip install` and go.
- (+) Metadata stored alongside vectors — citations come for free at query time.
- (−) Limited to single-process writes. Acceptable: ingestion is offline.
- (−) Less performant at scale than Qdrant. Acceptable: target corpus is small.

Final decision documented in Step 4 with benchmarks.
