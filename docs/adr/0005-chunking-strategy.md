# ADR 0005 — Section-aware chunking for RFCs

- **Status:** Accepted
- **Date:** 2026-06-15

## Context

Chunking is the highest-leverage decision in a RAG pipeline. Bad chunking
makes good retrieval impossible no matter how strong the embedding or
reranker is. The corpus (RFCs from Step 2) has unusually regular structure
that we should exploit:

- Numbered, hierarchical sections (`§4.1.1 Authorization Code Grant`).
- Hard semantic boundaries between sections (definitions, registry tables,
  algorithms, security considerations) that fixed-size chunkers happily slice
  through.
- Citations are *expected* to point to a specific section + page (`RFC 6749
  §4.1.1 p.25`), and an interview reviewer can spot-check those citations
  manually.

## Decision

Two-layer chunker:

1. **Section-aware outer loop.** Iterate the parsed `Section` objects in
   document order. **Never split across section boundaries.** Each chunk
   inherits the section's `{number, title, page_start, page_end}` so
   citations are unambiguous.

2. **Recursive splitter inner loop.** When a section exceeds
   `chunk_size_tokens`, split it using a separator chain
   `["\n\n", "\n", ". ", "; ", ", ", " ", ""]`. Pieces are merged greedily
   into chunks of up to `chunk_size_tokens` tokens with `chunk_overlap_tokens`
   of trailing context carried into the next chunk.

3. **Tokenizer.** `tiktoken` `cl100k_base` (GPT-3.5/4 BPE). Counting in
   tokens matches what the LLM ultimately sees and avoids the gross errors
   that character or word counts produce on dense technical text.

4. **Content-addressed `chunk_id`.** `sha256(doc_id + section_id +
   chunk_index_in_section + text)`. Re-running the chunker on identical
   input yields identical ids, which is what makes the index in Step 4
   cache-friendly.

5. **Manifest hash chain.** `chunk_manifest_sha256` covers the chunking
   config + every chunk_id, layered on top of the ingestion manifest's
   `manifest_sha256`. Step 4 keys the ChromaDB collection name on this hash
   so the index automatically rebuilds when *any* upstream input changes.

## Default parameters

`chunk_size_tokens=512`, `chunk_overlap_tokens=64`, `min_chunk_tokens=32`.

These are conservative-baseline choices, not optimized:

- 512 fits well inside the 8 K context windows our free-tier LLMs offer
  even after concatenating top-5 chunks plus the prompt.
- 64-token overlap (~12.5%) preserves enough cross-boundary context for
  multi-sentence definitions to remain searchable from either side of a
  split.
- A formal chunk-size ablation against the eval set lands in **Step 9
  polish**, where the result will be: a table of (chunk_size, faithfulness,
  context_recall) on the golden set, committed as part of the README.

## Alternatives considered

1. **Fixed-size chunking only** (LangChain's `RecursiveCharacterTextSplitter`
   over the full document). Simple, universally applicable, throws away the
   single most important piece of metadata RFCs give us. Rejected.

2. **Sentence-window chunking** (each chunk = one sentence + its neighbors).
   Better local coherence; worse retrieval recall on multi-sentence
   concepts. Most RFC definitions span 2–5 sentences so an embedding of a
   single sentence loses too much context. Rejected.

3. **Semantic chunking** (embedding-similarity boundaries). Non-deterministic
   given embedding-model changes, hard to debug, doesn't materially help on
   pre-structured corpora. Reconsider at Step 9 polish if eval shows recall
   problems we can't fix elsewhere.

4. **Use LangChain's chunker.** Re-implementing in <100 lines that we own
   removes a dependency surface, lets us match its behavior exactly in tests,
   and makes it trivial to add corpus-specific tweaks (RFC ABNF blocks,
   markdown header awareness in a follow-up) without forking upstream.

## Consequences

- (+) Citations are accurate and verifiable: every chunk knows its
  `(doc_id, section_number, page)` triple. The citation-existence layer in
  ADR 0006 has the metadata it needs.
- (+) Retrieval recall improves on multi-section concepts because each chunk
  is self-contained — embedded with its full section context.
- (+) Idempotent: same input → same chunk_ids → same index. CI rebuild key
  is `chunk_manifest_sha256`.
- (−) The recursive splitter is bespoke code we own. Mitigated by 25 unit
  tests covering the boundary cases (oversized sections, unicode width,
  separator preservation, overlap correctness, empty/whitespace edge cases).
- (−) Tokenizer is a runtime dependency. Acceptable: `tiktoken` is ~1 MB,
  pure Rust, vendors `cl100k_base` in the wheel (no network on first use).
