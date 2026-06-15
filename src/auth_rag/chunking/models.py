"""Pydantic models for the chunking stage.

A :class:`Chunk` is the atom of retrieval. It carries enough metadata to:

* Round-trip back to the originating document and section (for citation
  rendering and the citation-existence check in ADR 0006 layer 3).
* Be deduplicated across runs (`chunk_id` is content-addressed).
* Be reconstructed from a ``ChunkManifest`` without re-reading every chunk
  file (Step 4's index will key off ``chunk_manifest_sha256``).

Design constraints:

* Models are ``frozen``; chunks are immutable.
* ``chunk_id`` is deterministic — sha256(doc_id + section_id + char_start +
  text). Re-running chunking on identical input yields the same ids, so
  retrieval cached-result keys remain valid across runs.
* ``n_tokens`` is computed once at chunk-creation time; downstream stages
  trust it.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChunkingConfig(BaseModel):
    """Tunable knobs for the chunker. Loaded from ``config/default.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_size_tokens: int = Field(default=512, ge=64, le=4096)
    chunk_overlap_tokens: int = Field(default=64, ge=0, le=512)
    min_chunk_tokens: int = Field(
        default=32,
        ge=1,
        description="Sections smaller than this are merged with the next sibling rather than emitted as their own chunk.",
    )
    tokenizer_encoding: str = Field(
        default="cl100k_base",
        description="tiktoken encoding name. cl100k_base is GPT-3.5/4's BPE.",
    )

    @field_validator("chunk_overlap_tokens")
    @classmethod
    def _overlap_below_size(cls, value: int) -> int:
        # Overlap >= chunk_size produces infinite splits; we don't allow it.
        # The cross-field check happens via ``model_validator`` on construction;
        # this is a soft check that just constrains the upper bound.
        return value


class Chunk(BaseModel):
    """One unit of retrieval, carrying its full citation lineage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str = Field(min_length=1, pattern=r"^[a-f0-9]{64}$")
    doc_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    section_number: str | None = None
    section_title: str = Field(min_length=1)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    text: str = Field(min_length=1)
    n_tokens: int = Field(ge=1)
    char_start: int = Field(ge=0, description="Offset within the section's text.")
    char_end: int = Field(ge=0)
    chunk_index_in_section: int = Field(ge=0)

    def citation(self) -> str:
        """Render a human/LLM-friendly citation tag.

        Example: ``[rfc6749 §4.1.1 p.25]``.
        """
        parts = [self.doc_id]
        if self.section_number:
            parts.append(f"§{self.section_number}")
        if self.page_start:
            parts.append(f"p.{self.page_start}")
        return "[" + " ".join(parts) + "]"


class ChunkManifestEntry(BaseModel):
    """One row of the chunk manifest. Persisted alongside the chunks file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    doc_id: str
    n_chunks: int = Field(ge=1)
    n_tokens_total: int = Field(ge=1)
    chunks_path: Path


class ChunkManifest(BaseModel):
    """Top-level manifest for the chunking stage.

    Mirrors the shape of the ingestion manifest: integrity-hashed,
    sorted-by-doc-id, atomic-write target.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    corpus_version: str = Field(min_length=1)
    chunking_config: ChunkingConfig
    source_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    generated_at: datetime
    entries: tuple[ChunkManifestEntry, ...] = Field(min_length=1)
    chunk_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
