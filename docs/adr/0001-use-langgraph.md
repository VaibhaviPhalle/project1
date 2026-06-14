# ADR 0001 — Use LangGraph over plain LangChain for orchestration

- **Status:** Accepted
- **Date:** 2026-06-14

## Context

The retrieval pipeline grows in complexity across phases:

- Phase 1: Query → vector retrieve → generate.
- Phase 2: + sparse retrieve, + RRF fusion, + reranking, + citation verification, + claim-level NLI check, + fallback to "insufficient context".
- Phase 3: + per-stage tracing for eval.

A linear `Chain` quickly becomes a god-object with conditional branches buried
in callbacks. Stage outputs (top-k, scores, citations, NLI evidence) need to
flow forward and be inspected in tests.

## Decision

Use **LangGraph** as the orchestration layer. Each pipeline stage is a node;
state is a single typed Pydantic object passed between nodes; conditional
edges express "if no chunks above threshold → refuse" cleanly.

## Alternatives considered

1. **Plain LangChain `RunnableSequence`** — fine for the linear case, but the
   conditional branches (refuse-on-empty, repair-malformed-LLM-output, fallback
   provider chain) require nested `RunnableBranch`/`RunnableLambda` that hide
   control flow.
2. **Hand-rolled orchestration** (just functions and `if` statements) — cleanest
   for a tiny project, but loses out-of-the-box tracing, persistence, and
   visualization that interviewers can be shown.
3. **Haystack pipelines** — capable equivalent. Dropped because the LangGraph
   ecosystem (LangSmith tracing, prebuilt integrations) is more compelling as a
   portfolio signal in 2026.

## Consequences

- (+) Visualizable graph (`graph.get_graph().draw_mermaid()`) — included in README.
- (+) State is a Pydantic model — typed, validated, easy to snapshot for tests.
- (+) First-class conditional edges → no nested callbacks for "refuse on empty".
- (−) Extra concept to learn for contributors. Mitigated by keeping nodes as
  small, side-effect-free pure functions and documenting the state schema.
- (−) Pinning to `langgraph` for now; if the API destabilizes the upgrade may be
  noisy. Mitigated by isolating LangGraph wiring to ``src/auth_rag/graph/``.
