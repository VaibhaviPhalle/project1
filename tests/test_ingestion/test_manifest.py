"""Tests for manifest read/write and hash chain."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from auth_rag.exceptions import IngestionError
from auth_rag.ingestion.manifest import MANIFEST_FILENAME, read_manifest, write_manifest
from auth_rag.ingestion.models import License, ManifestEntry, SourceKind


def _entry(doc_id: str, *, sha: str = "a" * 64, fetched: datetime | None = None) -> ManifestEntry:
    return ManifestEntry(
        doc_id=doc_id,
        title=f"Title {doc_id}",
        kind=SourceKind.RFC_TXT,
        source_url=f"https://example.com/{doc_id}.txt",
        license=License.PUBLIC_DOMAIN,
        sha256=sha,
        fetched_at=fetched or datetime.now(UTC),
        n_sections=3,
        n_chars=1000,
        raw_path=Path(f"/tmp/{doc_id}.txt"),
        processed_dir=Path(f"/tmp/{doc_id}"),
    )


@pytest.mark.unit
def test_round_trip(tmp_path: Path) -> None:
    written = write_manifest(
        entries=[_entry("rfc6749"), _entry("rfc7519")],
        corpus_version="v1",
        processed_dir=tmp_path,
    )
    loaded = read_manifest(tmp_path)
    assert loaded.corpus_version == written.corpus_version
    assert loaded.manifest_sha256 == written.manifest_sha256
    assert [e.doc_id for e in loaded.entries] == ["rfc6749", "rfc7519"]


@pytest.mark.unit
def test_entries_are_sorted(tmp_path: Path) -> None:
    write_manifest(
        entries=[_entry("rfc7519"), _entry("rfc6749"), _entry("rfc7636")],
        corpus_version="v1",
        processed_dir=tmp_path,
    )
    m = read_manifest(tmp_path)
    assert [e.doc_id for e in m.entries] == ["rfc6749", "rfc7519", "rfc7636"]


@pytest.mark.unit
def test_hash_is_independent_of_fetched_at(tmp_path: Path) -> None:
    """Re-running ingest at a different time on identical content yields
    the same manifest_sha256. This is what lets the index cache be reused."""
    a = write_manifest(
        entries=[_entry("rfc6749", fetched=datetime(2026, 1, 1, tzinfo=UTC))],
        corpus_version="v1",
        processed_dir=tmp_path / "a",
    )
    b = write_manifest(
        entries=[_entry("rfc6749", fetched=datetime(2026, 6, 14, tzinfo=UTC))],
        corpus_version="v1",
        processed_dir=tmp_path / "b",
    )
    assert a.manifest_sha256 == b.manifest_sha256


@pytest.mark.unit
def test_hash_changes_when_content_changes(tmp_path: Path) -> None:
    a = write_manifest(
        entries=[_entry("rfc6749", sha="a" * 64)],
        corpus_version="v1",
        processed_dir=tmp_path / "a",
    )
    b = write_manifest(
        entries=[_entry("rfc6749", sha="b" * 64)],
        corpus_version="v1",
        processed_dir=tmp_path / "b",
    )
    assert a.manifest_sha256 != b.manifest_sha256


@pytest.mark.unit
def test_empty_manifest_rejected(tmp_path: Path) -> None:
    with pytest.raises(IngestionError, match="empty"):
        write_manifest(entries=[], corpus_version="v1", processed_dir=tmp_path)


@pytest.mark.unit
def test_missing_manifest_raises(tmp_path: Path) -> None:
    with pytest.raises(IngestionError, match="not found"):
        read_manifest(tmp_path)


@pytest.mark.unit
def test_tampered_manifest_detected(tmp_path: Path) -> None:
    write_manifest(
        entries=[_entry("rfc6749")],
        corpus_version="v1",
        processed_dir=tmp_path,
    )
    target = tmp_path / MANIFEST_FILENAME
    payload = target.read_text(encoding="utf-8")
    tampered = payload.replace('"corpus_version": "v1"', '"corpus_version": "v2"')
    target.write_text(tampered, encoding="utf-8")
    with pytest.raises(IngestionError, match="hash mismatch"):
        read_manifest(tmp_path)


@pytest.mark.unit
def test_malformed_json_raises(tmp_path: Path) -> None:
    (tmp_path / MANIFEST_FILENAME).write_text("not json", encoding="utf-8")
    with pytest.raises(IngestionError, match="invalid"):
        read_manifest(tmp_path)
