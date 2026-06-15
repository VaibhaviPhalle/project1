"""Tests for the section-aware chunker."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from auth_rag.chunking.models import ChunkingConfig
from auth_rag.chunking.section_aware import chunk_document
from auth_rag.ingestion.models import (
    License,
    ParsedDocument,
    Section,
    SourceKind,
)


def _doc_with_sections(*sections: Section) -> ParsedDocument:
    return ParsedDocument(
        doc_id="rfc9999",
        title="Test RFC",
        kind=SourceKind.RFC_TXT,
        source_url="https://example.com/rfc9999.txt",
        license=License.PUBLIC_DOMAIN,
        sha256="a" * 64,
        fetched_at=datetime.now(UTC),
        sections=sections,
        raw_char_count=10_000,
    )


def _section(
    *,
    section_id: str,
    number: str | None,
    title: str,
    text: str,
    page: int = 1,
) -> Section:
    return Section(
        section_id=section_id,
        number=number,
        title=title,
        text=text,
        page_start=page,
        page_end=page,
        char_start=0,
        char_end=len(text),
    )


@pytest.mark.unit
def test_short_section_emits_one_chunk() -> None:
    doc = _doc_with_sections(
        _section(section_id="1", number="1", title="Intro", text="A short section.")
    )
    chunks = chunk_document(doc, ConfigDefault())
    assert len(chunks) == 1
    assert chunks[0].section_number == "1"
    assert chunks[0].section_title == "Intro"
    assert chunks[0].chunk_index_in_section == 0


@pytest.mark.unit
def test_long_section_splits_but_inherits_metadata() -> None:
    long_text = ("This is a sentence in section 4. " * 200).strip()
    doc = _doc_with_sections(
        _section(
            section_id="4",
            number="4",
            title="Protocol",
            text=long_text,
            page=10,
        )
    )
    chunks = chunk_document(doc, ConfigDefault(chunk_size_tokens=100, chunk_overlap_tokens=10))
    assert len(chunks) > 1
    # Every chunk inherits the same section metadata.
    for c in chunks:
        assert c.section_id == "4"
        assert c.section_number == "4"
        assert c.section_title == "Protocol"
        assert c.page_start == 10
    # chunk_index_in_section is monotonic.
    indices = [c.chunk_index_in_section for c in chunks]
    assert indices == sorted(indices)
    assert len(set(indices)) == len(indices)


@pytest.mark.unit
def test_chunks_appear_in_section_order() -> None:
    doc = _doc_with_sections(
        _section(section_id="1", number="1", title="Intro", text="Intro content."),
        _section(section_id="2", number="2", title="Body", text="Body content."),
        _section(section_id="3", number="3", title="Tail", text="Tail content."),
    )
    chunks = chunk_document(doc, ConfigDefault())
    section_ids_in_order = [c.section_id for c in chunks]
    assert section_ids_in_order == ["1", "2", "3"]


@pytest.mark.unit
def test_chunk_id_is_deterministic() -> None:
    doc = _doc_with_sections(
        _section(section_id="1", number="1", title="Intro", text="Content here.")
    )
    a = chunk_document(doc, ConfigDefault())
    b = chunk_document(doc, ConfigDefault())
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]


@pytest.mark.unit
def test_chunk_id_changes_when_text_changes() -> None:
    a_doc = _doc_with_sections(
        _section(section_id="1", number="1", title="Intro", text="Original.")
    )
    b_doc = _doc_with_sections(
        _section(section_id="1", number="1", title="Intro", text="Modified.")
    )
    a = chunk_document(a_doc, ConfigDefault())
    b = chunk_document(b_doc, ConfigDefault())
    assert a[0].chunk_id != b[0].chunk_id


@pytest.mark.unit
def test_chunk_id_distinguishes_indices_within_section() -> None:
    long_text = ("Sentence in section. " * 200).strip()
    doc = _doc_with_sections(_section(section_id="1", number="1", title="Long", text=long_text))
    chunks = chunk_document(doc, ConfigDefault(chunk_size_tokens=80, chunk_overlap_tokens=10))
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


@pytest.mark.unit
def test_citation_is_well_formed() -> None:
    doc = _doc_with_sections(
        _section(section_id="4_1_1", number="4.1.1", title="ACG", text="Text.", page=25)
    )
    chunks = chunk_document(doc, ConfigDefault())
    assert chunks[0].citation() == "[rfc9999 §4.1.1 p.25]"


@pytest.mark.unit
def test_section_without_number_still_chunked() -> None:
    doc = _doc_with_sections(
        _section(section_id="front_matter", number=None, title="Front Matter", text="x" * 20)
    )
    chunks = chunk_document(doc, ConfigDefault())
    assert len(chunks) == 1
    assert chunks[0].section_number is None


@pytest.mark.unit
def test_n_tokens_set_per_chunk() -> None:
    long_text = ("Some sentence. " * 100).strip()
    doc = _doc_with_sections(_section(section_id="1", number="1", title="L", text=long_text))
    chunks = chunk_document(doc, ConfigDefault(chunk_size_tokens=100, chunk_overlap_tokens=10))
    for c in chunks:
        assert c.n_tokens >= 1
        assert c.n_tokens <= 100


def ConfigDefault(**kwargs: object) -> ChunkingConfig:
    """Build a ChunkingConfig with sensible test defaults."""
    base: dict[str, object] = {
        "chunk_size_tokens": 512,
        "chunk_overlap_tokens": 64,
    }
    base.update(kwargs)
    return ChunkingConfig(**base)  # type: ignore[arg-type]
