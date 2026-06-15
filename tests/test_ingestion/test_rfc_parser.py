"""Tests for the section-aware RFC parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from auth_rag.exceptions import IngestionError
from auth_rag.ingestion.models import License, SourceKind, SourceSpec
from auth_rag.ingestion.rfc_parser import parse_rfc
from tests.fixtures.sample_rfc import SAMPLE_RFC_TXT


@pytest.fixture
def sample_path(tmp_path: Path) -> Path:
    p = tmp_path / "rfc9999.txt"
    p.write_text(SAMPLE_RFC_TXT, encoding="utf-8")
    return p


@pytest.fixture
def sample_spec() -> SourceSpec:
    return SourceSpec(
        doc_id="rfc9999",
        title="A Sample RFC for Parser Testing",
        kind=SourceKind.RFC_TXT,
        source_url="https://example.com/rfc9999.txt",
        license=License.PUBLIC_DOMAIN,
    )


@pytest.mark.unit
def test_parses_expected_section_count(sample_spec: SourceSpec, sample_path: Path) -> None:
    doc = parse_rfc(sample_spec, sample_path)
    numbers = [s.number for s in doc.sections if s.number is not None]
    # Five numbered sections in the fixture: 1, 2, 3, 3.1, 3.2, 4.
    assert "1" in numbers
    assert "3.1" in numbers
    assert "3.2" in numbers
    assert "4" in numbers


@pytest.mark.unit
def test_section_titles_extracted(sample_spec: SourceSpec, sample_path: Path) -> None:
    doc = parse_rfc(sample_spec, sample_path)
    by_number = {s.number: s for s in doc.sections}
    assert by_number["1"].title == "Introduction"
    assert by_number["3.1"].title == "Step One"
    assert by_number["4"].title == "Security Considerations"


@pytest.mark.unit
def test_page_numbers_assigned(sample_spec: SourceSpec, sample_path: Path) -> None:
    doc = parse_rfc(sample_spec, sample_path)
    by_number = {s.number: s for s in doc.sections}
    # Section 1 ("Introduction") starts on page 2 in the fixture.
    assert by_number["1"].page_start == 2
    # Section 4 ("Security Considerations") is on page 4.
    assert by_number["4"].page_start == 4


@pytest.mark.unit
def test_parent_section_id_set_for_subsections(sample_spec: SourceSpec, sample_path: Path) -> None:
    doc = parse_rfc(sample_spec, sample_path)
    by_number = {s.number: s for s in doc.sections}
    # 3.1 and 3.2 should be children of section 3.
    assert by_number["3.1"].parent_section_id == by_number["3"].section_id
    assert by_number["3.2"].parent_section_id == by_number["3"].section_id
    # Section 1 has no parent.
    assert by_number["1"].parent_section_id is None


@pytest.mark.unit
def test_table_of_contents_does_not_create_duplicate_sections(
    sample_spec: SourceSpec, sample_path: Path
) -> None:
    doc = parse_rfc(sample_spec, sample_path)
    numbered = [s.number for s in doc.sections if s.number is not None]
    # Each number appears at most once even though it shows up in the TOC.
    assert len(numbered) == len(set(numbered))


@pytest.mark.unit
def test_metadata_extracted(sample_spec: SourceSpec, sample_path: Path) -> None:
    doc = parse_rfc(sample_spec, sample_path)
    assert doc.metadata.get("rfc_number") == "9999"
    assert "Standards Track" in doc.metadata.get("category", "")
    assert doc.metadata.get("stream") == "IETF"


@pytest.mark.unit
def test_sha256_is_deterministic(sample_spec: SourceSpec, sample_path: Path) -> None:
    a = parse_rfc(sample_spec, sample_path)
    b = parse_rfc(sample_spec, sample_path)
    assert a.sha256 == b.sha256


@pytest.mark.unit
def test_empty_file_raises(tmp_path: Path, sample_spec: SourceSpec) -> None:
    p = tmp_path / "empty.txt"
    p.write_text("", encoding="utf-8")
    with pytest.raises(IngestionError, match="empty"):
        parse_rfc(sample_spec, p)


@pytest.mark.unit
def test_missing_file_raises(tmp_path: Path, sample_spec: SourceSpec) -> None:
    with pytest.raises(IngestionError, match="cannot read"):
        parse_rfc(sample_spec, tmp_path / "nope.txt")


@pytest.mark.unit
def test_wrong_kind_rejected(sample_path: Path) -> None:
    spec = SourceSpec(
        doc_id="x",
        title="t",
        kind=SourceKind.MARKDOWN,
        source_url="https://x",
        license=License.PUBLIC_DOMAIN,
    )
    with pytest.raises(IngestionError, match="non-RFC"):
        parse_rfc(spec, sample_path)


@pytest.mark.unit
def test_unrecognized_format_falls_back_to_front_matter(
    tmp_path: Path, sample_spec: SourceSpec
) -> None:
    p = tmp_path / "weird.txt"
    p.write_text("just some\nplain text\nwith no sections at all.\n", encoding="utf-8")
    doc = parse_rfc(sample_spec, p)
    assert len(doc.sections) == 1
    assert doc.sections[0].section_id == "front_matter"


@pytest.mark.unit
def test_section_offsets_within_raw(sample_spec: SourceSpec, sample_path: Path) -> None:
    doc = parse_rfc(sample_spec, sample_path)
    raw = sample_path.read_text(encoding="utf-8")
    for s in doc.sections:
        if s.number is not None:
            # The number should appear at or near the recorded char_start.
            window = raw[s.char_start : s.char_start + 80]
            assert s.number in window
