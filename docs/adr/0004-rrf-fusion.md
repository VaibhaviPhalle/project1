# ADR 0004 — Hybrid retrieval with RRF over weighted score fusion

- **Status:** Proposed (finalized in Step 6)
- **Date:** 2026-06-14

## Context

Hybrid retrieval combines BM25 (sparse) and dense vector retrieval. The two
score scales are not directly comparable — BM25 scores are unbounded TF-IDF
sums; vector scores are cosine similarities in [-1, 1].

## Decision (preliminary)

Use **Reciprocal Rank Fusion (RRF)** with `k=60` (Cormack et al., 2009). Combine
the two ranked lists by summing `1 / (k + rank_i)` per document.

## Alternatives considered

1. **Weighted score fusion** (`α * dense + (1 - α) * sparse_norm`) — requires
   per-corpus tuning of the score normalization and weight. Sensitive to
   distribution shifts as the corpus grows.
2. **Learning to rank** — overkill at this corpus size and adds a training
   pipeline.

## Consequences

- (+) Parameter-free, well-studied, robust to score distribution.
- (+) Easy to explain in interviews.
- (−) Cannot leverage absolute score gaps. Mitigated by reranker downstream.

Final decision with eval numbers documented in Step 6.
