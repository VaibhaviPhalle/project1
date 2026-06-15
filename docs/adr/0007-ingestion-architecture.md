# ADR 0007 — Ingestion architecture: declarative corpus + section-aware parsing

- **Status:** Accepted
- **Date:** 2026-06-14

## Context

The retrieval pipeline only retrieves what ingestion produces. Subtle bugs
here — wrong section boundaries, hallucinated metadata, silent corpus drift —
become "the model is hallucinating" symptoms downstream that take far more
effort to diagnose than to prevent.

Two design questions drove this step:

1. **How is "what's in the corpus" represented?**
2. **How do we parse RFCs into something better than fixed-size text chunks?**

## Decision

### 1. Declarative corpus + manifest-as-truth

`config/corpus.yaml` is the **only** place where source documents are
declared. Every spec carries `{doc_id, title, kind, source_url, license,
expected_sha256?}`. Downstream stages never inspect `data/raw/`; they read
`data/processed/manifest.json`, which the ingestion pipeline writes
atomically after every source has been processed successfully.

The manifest carries:

- A per-entry `sha256` of the fetched bytes.
- A top-level `manifest_sha256` over the canonical entries blob (excluding
  `fetched_at`) so re-running ingest on identical content reproduces the same
  hash. This is the cache key for the index in Step 4 and the gate the CI
  eval in Step 7 uses to decide whether to rebuild.

### 2. Section-aware parsing

The RFC parser exploits the canonical RFC text format:

- Section headers (`4.1.1 Authorization Code Grant`).
- Page-break form-feeds and `[Page N]` footers.
- The `Request for Comments: NNNN` / `Category:` metadata block.

Each `Section` carries `{number, title, page_start, page_end, char_start,
char_end, parent_section_id}` so retrieval can render
`[RFC 6749 §4.1.1 p.25]` citations *exactly* — no LLM guesswork required.

The chunker (Step 3) will chunk *within* sections, never across them.

### 3. Defensive boundaries

- Atomic file writes via `.part` rename.
- HTTP retries with exponential backoff (`tenacity`).
- A 50 MB hard cap per download (a misconfigured URL can't fill the disk).
- An `AUTH_RAG_OFFLINE=1` kill switch (default in CI) refuses any HTTP call.
- A regex PII scrubber (emails, non-doc IPs) runs over every section before
  persistence. RFC 5737 documentation IPs are explicitly preserved.

## Alternatives considered

1. **No manifest, just walk `data/processed/` at retrieval time.** Simpler
   today, fragile tomorrow. The "is this index in sync with the corpus?"
   question is the single most common source of "stale answers" in production
   RAG. Cheaper to solve once than to debug under pressure.
2. **Fixed-size chunking now, section metadata later.** Fixed-size chunking
   destroys exactly the structural metadata that makes RFC citations
   trustworthy. Retrofitting metadata after losing it is far more expensive
   than parsing structurally up-front.
3. **Use `langchain_community.document_loaders.RFCLoader`** (or similar).
   None exist with the metadata fidelity we need (page numbers, hierarchical
   section ids), and we'd inherit a transitive dep we otherwise avoid.

## Consequences

- (+) Citations are exact; the four-layer enforcement in ADR 0006 has the
      metadata it needs to verify cited sections actually exist.
- (+) Corpus drift is detectable: any change to `corpus.yaml` or any source's
      bytes changes `manifest_sha256`, which forces an index rebuild.
- (+) Idempotent re-runs: cached files with matching hashes are no-ops,
      enabling fast dev loops.
- (−) The RFC parser is a bespoke component we own. Mitigated by keeping it
      small (~200 lines), pure-functional, and well tested.
- (−) Markdown / HTML / PDF parsers are deferred to a follow-up PR. Step 2
      is RFCs only; the eval set in Step 7 will ship with whatever's
      ingested by then.
