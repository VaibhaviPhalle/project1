"""Tests for the chunking Pydantic models."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from auth_rag.chunking.models import (
    Chunk,
    ChunkingConfig,
    ChunkManifest,
    ChunkManifestEntry,
)


def _chunk(**overrides: object) -> Chunk:
    base: dict[str, object] = {
        "chunk_id": "a" * 64,
        "doc_id": "rfc6749",
        "section_id": "4_1_1",
        "section_number": "4.1.1",
        "section_title": "Authorization Code Grant",
        "page_start": 25,
        "page_end": 25,
        "text": "The authorization code grant type is used...",
        "n_tokens": 12,
        "char_start": 0,
        "char_end": 50,
        "chunk_index_in_section": 0,
    }
    base.update(overrides)
    return Chunk(**base)  # type: ignore[arg-type]


@pytest.mark.unit
def test_chunk_immutable() -> None:
    c = _chunk()
    with pytest.raises(ValidationError):
        c.text = "mutated"  # type: ignore[misc]


@pytest.mark.unit
def test_chunk_id_must_be_64_hex() -> None:
    with pytest.raises(ValidationError):
        _chunk(chunk_id="not-a-hash")


@pytest.mark.unit
def test_n_tokens_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _chunk(n_tokens=0)


@pytest.mark.unit
def test_text_must_be_nonempty() -> None:
    with pytest.raises(ValidationError):
        _chunk(text="")


@pytest.mark.unit
def test_citation_format_with_section_and_page() -> None:
    c = _chunk()
    assert c.citation() == "[rfc6749 §4.1.1 p.25]"


@pytest.mark.unit
def test_citation_format_without_section() -> None:
    c = _chunk(section_number=None, page_start=None)
    assert c.citation() == "[rfc6749]"


@pytest.mark.unit
def test_citation_format_with_section_no_page() -> None:
    c = _chunk(page_start=None)
    assert c.citation() == "[rfc6749 §4.1.1]"


@pytest.mark.unit
def test_chunking_config_rejects_overlap_too_large() -> None:
    # Overlap >= chunk_size is allowed by the field validator (we don't enforce
    # cross-field), but the recursive splitter rejects it at runtime. The
    # field itself caps at 512 anyway.
    with pytest.raises(ValidationError):
        ChunkingConfig(chunk_size_tokens=128, chunk_overlap_tokens=600)


@pytest.mark.unit
def test_chunking_config_defaults() -> None:
    c = ChunkingConfig()
    assert c.chunk_size_tokens == 512
    assert c.chunk_overlap_tokens == 64
    assert c.tokenizer_encoding == "cl100k_base"


@pytest.mark.unit
def test_chunk_manifest_round_trip() -> None:
    entry = ChunkManifestEntry(
        doc_id="rfc6749",
        n_chunks=10,
        n_tokens_total=4096,
        chunks_path=Path("/tmp/rfc6749/chunks.jsonl"),
    )
    m = ChunkManifest(
        corpus_version="v1",
        chunking_config=ChunkingConfig(),
        source_manifest_sha256="a" * 64,
        generated_at=datetime.now(UTC),
        entries=(entry,),
        chunk_manifest_sha256="b" * 64,
    )
    blob = m.model_dump_json()
    m2 = ChunkManifest.model_validate_json(blob)
    assert m == m2
