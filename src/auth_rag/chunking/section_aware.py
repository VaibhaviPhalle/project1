"""Section-aware chunker.

Per ADR 0005, we **never split across sections**. The contract:

  * If a section's text fits in the chunk-size budget, emit it as a single
    chunk.
  * If a section is larger than the budget, split it using the recursive
    splitter; every resulting chunk inherits the *same* section metadata
    (number, title, page) so citations remain unambiguous.
  * If a section is smaller than ``min_chunk_tokens`` (e.g. an empty stub
    or a 1-line subsection), it's still emitted — better tiny than lost
    for retrieval recall on short definitions.

``chunk_id`` is content-addressed:
``sha256(doc_id + section_id + chunk_index_in_section + text)``. Re-running
the chunker on identical input yields identical ids, which is what
makes the index in Step 4 cache-friendly.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import TYPE_CHECKING

from auth_rag.chunking.models import Chunk
from auth_rag.chunking.recursive import split_text
from auth_rag.chunking.tokenizer import get_tokenizer

if TYPE_CHECKING:
    from auth_rag.chunking.models import ChunkingConfig
    from auth_rag.ingestion.models import ParsedDocument, Section


def chunk_document(doc: ParsedDocument, config: ChunkingConfig) -> list[Chunk]:
    """Chunk a :class:`ParsedDocument` into a list of :class:`Chunk` objects.

    Returns chunks in document order: outer loop over sections (in source
    order), inner loop over within-section splits.
    """
    tokenizer = get_tokenizer(config.tokenizer_encoding)
    out: list[Chunk] = []
    for section in doc.sections:
        out.extend(
            _chunk_section(
                section=section,
                doc_id=doc.doc_id,
                config=config,
                tokenizer_count=tokenizer.count,
                splitter=lambda t: split_text(
                    t,
                    tokenizer=tokenizer,
                    chunk_tokens=config.chunk_size_tokens,
                    overlap_tokens=config.chunk_overlap_tokens,
                ),
            )
        )
    return out


def _chunk_section(
    *,
    section: Section,
    doc_id: str,
    config: ChunkingConfig,
    tokenizer_count: Callable[[str], int],
    splitter: Callable[[str], list[str]],
) -> list[Chunk]:
    n_tokens = tokenizer_count(section.text)
    if n_tokens <= config.chunk_size_tokens:
        return [
            _build_chunk(
                doc_id=doc_id,
                section=section,
                text=section.text,
                n_tokens=n_tokens,
                char_offset_in_section=0,
                chunk_index=0,
            )
        ]

    pieces = splitter(section.text)
    chunks: list[Chunk] = []
    cursor = 0
    for idx, piece in enumerate(pieces):
        # Find the piece's offset within the section text. Recursive splitter
        # preserves separators, so the original text is reconstructible by
        # concatenation -- pieces appear in order.
        offset = section.text.find(piece, cursor)
        if offset == -1:
            offset = cursor
        cursor = offset + len(piece)
        chunks.append(
            _build_chunk(
                doc_id=doc_id,
                section=section,
                text=piece,
                n_tokens=tokenizer_count(piece),
                char_offset_in_section=offset,
                chunk_index=idx,
            )
        )
    return chunks


def _build_chunk(
    *,
    doc_id: str,
    section: Section,
    text: str,
    n_tokens: int,
    char_offset_in_section: int,
    chunk_index: int,
) -> Chunk:
    chunk_id = _content_hash(
        doc_id=doc_id,
        section_id=section.section_id,
        chunk_index=chunk_index,
        text=text,
    )
    return Chunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        section_id=section.section_id,
        section_number=section.number,
        section_title=section.title,
        page_start=section.page_start,
        page_end=section.page_end,
        text=text,
        n_tokens=max(n_tokens, 1),
        char_start=char_offset_in_section,
        char_end=char_offset_in_section + len(text),
        chunk_index_in_section=chunk_index,
    )


def _content_hash(*, doc_id: str, section_id: str, chunk_index: int, text: str) -> str:
    h = hashlib.sha256()
    h.update(doc_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(section_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(str(chunk_index).encode("utf-8"))
    h.update(b"\x00")
    h.update(text.encode("utf-8"))
    return h.hexdigest()
