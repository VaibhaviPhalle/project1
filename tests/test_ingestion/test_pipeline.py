"""End-to-end tests for the ingestion pipeline (offline)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from auth_rag.exceptions import IngestionError
from auth_rag.ingestion import downloader
from auth_rag.ingestion.corpus_config import CorpusConfig
from auth_rag.ingestion.manifest import read_manifest
from auth_rag.ingestion.models import License, SourceKind, SourceSpec
from auth_rag.ingestion.pipeline import ingest
from tests.fixtures.sample_rfc import SAMPLE_RFC_TXT


def _config() -> CorpusConfig:
    return CorpusConfig(
        corpus_version="vtest",
        sources=(
            SourceSpec(
                doc_id="rfc9999",
                title="Sample",
                kind=SourceKind.RFC_TXT,
                source_url="https://example.com/rfc9999.txt",
                license=License.PUBLIC_DOMAIN,
            ),
        ),
    )


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def patched(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(downloader.httpx, "Client", patched)


@pytest.mark.unit
def test_full_pipeline_writes_manifest_and_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AUTH_RAG_OFFLINE", raising=False)
    _install_transport(
        monkeypatch,
        lambda _: httpx.Response(200, content=SAMPLE_RFC_TXT.encode("utf-8")),
    )

    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    manifest = ingest(config=_config(), raw_dir=raw, processed_dir=processed)

    # Manifest has one entry.
    assert len(manifest.entries) == 1
    entry = manifest.entries[0]
    assert entry.doc_id == "rfc9999"
    assert entry.n_sections >= 4

    # Manifest survives a round-trip.
    loaded = read_manifest(processed)
    assert loaded.manifest_sha256 == manifest.manifest_sha256

    # Section files were written.
    sections_dir = processed / "rfc9999" / "sections"
    assert sections_dir.is_dir()
    assert any(sections_dir.glob("*.txt"))
    assert (processed / "rfc9999" / "document.json").is_file()


@pytest.mark.unit
def test_scrubbing_is_applied_in_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTH_RAG_OFFLINE", raising=False)
    _install_transport(
        monkeypatch,
        lambda _: httpx.Response(200, content=SAMPLE_RFC_TXT.encode("utf-8")),
    )

    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    ingest(config=_config(), raw_dir=raw, processed_dir=processed)

    section_files = list((processed / "rfc9999" / "sections").glob("*.txt"))
    combined = "\n".join(p.read_text(encoding="utf-8") for p in section_files)
    # Email in the fixture must be redacted.
    assert "alice@example.org" not in combined
    assert "bob@example.com" not in combined
    assert "[email-redacted]" in combined
    # Documentation IP (192.0.2.1) must be preserved.
    assert "192.0.2.1" in combined
    # Non-doc IP (10.0.0.5) must be redacted.
    assert "10.0.0.5" not in combined


@pytest.mark.unit
def test_only_filter_selects_subset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTH_RAG_OFFLINE", raising=False)
    _install_transport(
        monkeypatch,
        lambda _: httpx.Response(200, content=SAMPLE_RFC_TXT.encode("utf-8")),
    )

    config = CorpusConfig(
        corpus_version="vtest",
        sources=(
            SourceSpec(
                doc_id="rfc9999",
                title="A",
                kind=SourceKind.RFC_TXT,
                source_url="https://example.com/rfc9999.txt",
                license=License.PUBLIC_DOMAIN,
            ),
            SourceSpec(
                doc_id="rfc8888",
                title="B",
                kind=SourceKind.RFC_TXT,
                source_url="https://example.com/rfc8888.txt",
                license=License.PUBLIC_DOMAIN,
            ),
        ),
    )

    manifest = ingest(
        config=config,
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        only=["rfc9999"],
    )
    assert {e.doc_id for e in manifest.entries} == {"rfc9999"}


@pytest.mark.unit
def test_unknown_only_doc_id_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTH_RAG_OFFLINE", raising=False)
    with pytest.raises(IngestionError, match="unknown doc_id"):
        ingest(
            config=_config(),
            raw_dir=tmp_path / "raw",
            processed_dir=tmp_path / "processed",
            only=["rfc-does-not-exist"],
        )
