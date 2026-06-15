"""Section-aware chunking.

Public entry point: :func:`chunk_corpus`. Composable internals are exposed
for testing and downstream stages.
"""

from __future__ import annotations

from auth_rag.chunking.models import (
    Chunk,
    ChunkingConfig,
    ChunkManifest,
    ChunkManifestEntry,
)
from auth_rag.chunking.pipeline import (
    chunk_corpus,
    read_chunk_manifest,
    read_chunks,
)
from auth_rag.chunking.section_aware import chunk_document
from auth_rag.chunking.tokenizer import Tokenizer, get_tokenizer

__all__ = [
    "Chunk",
    "ChunkManifest",
    "ChunkManifestEntry",
    "ChunkingConfig",
    "Tokenizer",
    "chunk_corpus",
    "chunk_document",
    "get_tokenizer",
    "read_chunk_manifest",
    "read_chunks",
]
