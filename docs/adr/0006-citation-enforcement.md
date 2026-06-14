# ADR 0006 — Four-layer citation enforcement

- **Status:** Proposed (finalized in Step 6)
- **Date:** 2026-06-14

## Context

A RAG system that confidently cites the wrong source — or invents citations
entirely — is worse than one that says "I don't know". This is the single
biggest failure mode of naive RAG and the single biggest "production
readiness" signal an interviewer looks for.

## Decision (preliminary)

Defense in depth — four independent layers, any one of which can refuse:

1. **Prompt-level.** System prompt mandates `[doc §section]` citations and
   prohibits using prior knowledge. Retrieved context is delimited with
   per-request random tokens to defeat prompt injection from poisoned chunks.
2. **Schema-level.** LLM output is forced through a Pydantic schema requiring
   `citations: list[Citation]` with `len >= 1` for non-empty answers.
3. **Existence-check.** Every cited `(doc_id, section)` is verified to exist in
   the corpus manifest. Hallucinated citations → reject and retry once, else
   refuse.
4. **Entailment-check.** A local NLI cross-encoder
   (`cross-encoder/nli-deberta-v3-base`) scores each answer sentence against
   the chunks it cites. Sentences below the entailment threshold are flagged.

A short-circuit precedes all four: if zero retrieved chunks exceed the
relevance threshold, return `"insufficient context"` without calling the LLM.

## Consequences

- (+) Hallucinated citations are caught even when the LLM is fluent.
- (+) The NLI verifier is local (free, no LLM calls), so the layer can run on
  every request without quota concerns.
- (−) Adds latency (~100ms for NLI on top-5 chunks). Acceptable for QA.
- (−) NLI false positives may flag legitimate paraphrases. Mitigated by
  threshold tuning during eval.

Final decision with measured before/after faithfulness in Step 6.
