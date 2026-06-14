# ADR 0005 — Section-aware chunking for RFCs

- **Status:** Proposed (finalized in Step 3)
- **Date:** 2026-06-14

## Context

RFCs follow a strict, regular structure: numbered sections (`§4.1.1`), formal
language, ABNF blocks, and explicit page boundaries. Naive fixed-size
chunking splits across these boundaries, producing chunks like
`...continues in section 4.1.2:\n4.1.2. Token Endpoint\nThe...` that confuse
both retrieval and the LLM's reading.

## Decision (preliminary)

Implement a **section-aware chunker** that:

1. Parses RFC structure first (section numbers, titles, page breaks).
2. Chunks within sections, never across them.
3. Tags every chunk with `{rfc_id, section_number, section_title, page}` for
   citation use downstream.
4. Falls back to recursive character splitting *within* a section if it exceeds
   the chunk-size budget.

Non-RFC sources (Auth0/Keycloak markdown) use header-aware splitting on
`#`/`##`/`###`.

## Alternatives considered

1. **Fixed-size recursive splitting** — universally applicable but loses the
   structural metadata that makes citations precise.
2. **Sentence-window chunking** — better local coherence but worse for
   retrieval recall on multi-sentence concepts (most RFC definitions span 2-5
   sentences).
3. **Semantic chunking** (embedding-similarity boundaries) — interesting but
   non-deterministic and hard to debug.

## Consequences

- (+) Citations are exact: `RFC 6749 §4.1.1 p.25` — interview-grade.
- (+) Retrieval recall improves on multi-section concepts because each chunk
  carries its full section context.
- (−) Custom parser per source type. Mitigated by keeping the parser small and
  testing each format.

Final decision with chunk-size ablation results in Step 3.
