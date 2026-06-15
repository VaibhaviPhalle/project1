"""Tests for the ingestion Pydantic models."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from auth_rag.ingestion.models import (
    License,
    Manifest,
    ManifestEntry,
    ParsedDocument,
    Section,
    SourceKind,
    SourceSpec,
)


@pytest.mark.unit
def test_source_spec_rejects_bad_doc_id() -> None:
    with pytest.raises(ValidationError):
        SourceSpec(
            doc_id="RFC 6749",  # spaces and uppercase not allowed
            title="bad",
            kind=SourceKind.RFC_TXT,
            source_url="https://example.com/x.txt",
            license=License.PUBLIC_DOMAIN,
        )


@pytest.mark.unit
def test_source_spec_validates_sha_pattern() -> None:
    with pytest.raises(ValidationError):
        SourceSpec(
            doc_id="rfc6749",
            title="x",
            kind=SourceKind.RFC_TXT,
            source_url="https://example.com/x.txt",
            license=License.PUBLIC_DOMAIN,
            expected_sha256="not-a-hash",
        )


@pytest.mark.unit
def test_source_spec_accepts_valid_hash() -> None:
    spec = SourceSpec(
        doc_id="rfc6749",
        title="x",
        kind=SourceKind.RFC_TXT,
        source_url="https://example.com/x.txt",
        license=License.PUBLIC_DOMAIN,
        expected_sha256="a" * 64,
    )
    assert spec.expected_sha256 is not None


@pytest.mark.unit
def test_section_immutability() -> None:
    s = Section(
        section_id="1",
        number="1",
        title="Intro",
        text="hello",
        char_start=0,
        char_end=5,
    )
    with pytest.raises(ValidationError):
        s.text = "mutated"  # type: ignore[misc]


@pytest.mark.unit
def test_parsed_document_rejects_zero_sections() -> None:
    with pytest.raises(ValidationError):
        ParsedDocument(
            doc_id="rfc",
            title="t",
            kind=SourceKind.RFC_TXT,
            source_url="https://x",
            license=License.PUBLIC_DOMAIN,
            sha256="a" * 64,
            fetched_at=datetime.now(UTC),
            sections=(),
            raw_char_count=0,
        )


@pytest.mark.unit
def test_manifest_entry_rejects_zero_sections() -> None:
    with pytest.raises(ValidationError):
        ManifestEntry(
            doc_id="rfc",
            title="t",
            kind=SourceKind.RFC_TXT,
            source_url="https://x",
            license=License.PUBLIC_DOMAIN,
            sha256="a" * 64,
            fetched_at=datetime.now(UTC),
            n_sections=0,
            n_chars=10,
            raw_path=Path("/tmp/x.txt"),
            processed_dir=Path("/tmp/proc"),
        )


@pytest.mark.unit
def test_manifest_round_trip() -> None:
    entry = ManifestEntry(
        doc_id="rfc",
        title="t",
        kind=SourceKind.RFC_TXT,
        source_url="https://x",
        license=License.PUBLIC_DOMAIN,
        sha256="a" * 64,
        fetched_at=datetime.now(UTC),
        n_sections=3,
        n_chars=100,
        raw_path=Path("/tmp/x.txt"),
        processed_dir=Path("/tmp/proc"),
    )
    m = Manifest(
        corpus_version="v1",
        generated_at=datetime.now(UTC),
        entries=(entry,),
        manifest_sha256="b" * 64,
    )
    blob = m.model_dump_json()
    m2 = Manifest.model_validate_json(blob)
    assert m == m2
