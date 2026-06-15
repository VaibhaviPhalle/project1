"""End-to-end tests for the chunking pipeline."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from auth_rag.chunking import ChunkingConfig, chunk_corpus, read_chunk_manifest, read_chunks
from auth_rag.chunking.pipeline import CHUNK_MANIFEST_FILENAME
from auth_rag.exceptions import IngestionError
from auth_rag.ingestion import downloader, ingest, load_corpus_config
from auth_rag.ingestion.manifest import write_manifest
from auth_rag.ingestion.models import License, ManifestEntry, SourceKind
from tests.fixtures.sample_rfc import SAMPLE_RFC_TXT


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


@pytest.fixture
def ingested_corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Run real ingestion against the sample RFC; return (raw, processed)."""
    monkeypatch.delenv("AUTH_RAG_OFFLINE", raising=False)
    _install_transport(
        monkeypatch,
        lambda _: httpx.Response(200, content=SAMPLE_RFC_TXT.encode("utf-8")),
    )
    config_path = tmp_path / "corpus.yaml"
    config_path.write_text(
        'corpus_version: "vtest"\n'
        "sources:\n"
        "  - doc_id: rfc9999\n"
        '    title: "Sample"\n'
        "    kind: rfc_txt\n"
        '    source_url: "https://example.com/rfc9999.txt"\n'
        "    license: public-domain\n",
        encoding="utf-8",
    )
    config = load_corpus_config(config_path)
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    ingest(config=config, raw_dir=raw, processed_dir=processed)
    return raw, processed


@pytest.mark.unit
def test_pipeline_writes_chunks_and_manifest(
    ingested_corpus: tuple[Path, Path], tmp_path: Path
) -> None:
    _, processed = ingested_corpus
    chunked = tmp_path / "chunked"
    manifest = chunk_corpus(
        config=ChunkingConfig(chunk_size_tokens=512, chunk_overlap_tokens=64),
        processed_dir=processed,
        chunked_dir=chunked,
    )

    assert len(manifest.entries) == 1
    entry = manifest.entries[0]
    assert entry.doc_id == "rfc9999"
    assert entry.n_chunks >= 1
    assert entry.chunks_path.is_file()

    # Round-trip the manifest through disk.
    loaded = read_chunk_manifest(chunked)
    assert loaded.chunk_manifest_sha256 == manifest.chunk_manifest_sha256

    # Chunks file is JSONL and parses cleanly.
    chunks = read_chunks(entry.chunks_path)
    assert len(chunks) == entry.n_chunks
    for c in chunks:
        assert c.doc_id == "rfc9999"
        assert c.text


@pytest.mark.unit
def test_chunk_manifest_hash_is_deterministic(
    ingested_corpus: tuple[Path, Path], tmp_path: Path
) -> None:
    _, processed = ingested_corpus
    a = chunk_corpus(
        config=ChunkingConfig(),
        processed_dir=processed,
        chunked_dir=tmp_path / "a",
    )
    b = chunk_corpus(
        config=ChunkingConfig(),
        processed_dir=processed,
        chunked_dir=tmp_path / "b",
    )
    assert a.chunk_manifest_sha256 == b.chunk_manifest_sha256


@pytest.mark.unit
def test_chunk_manifest_hash_changes_on_config_change(
    ingested_corpus: tuple[Path, Path], tmp_path: Path
) -> None:
    _, processed = ingested_corpus
    a = chunk_corpus(
        config=ChunkingConfig(chunk_size_tokens=256),
        processed_dir=processed,
        chunked_dir=tmp_path / "a",
    )
    b = chunk_corpus(
        config=ChunkingConfig(chunk_size_tokens=512),
        processed_dir=processed,
        chunked_dir=tmp_path / "b",
    )
    assert a.chunk_manifest_sha256 != b.chunk_manifest_sha256


@pytest.mark.unit
def test_unknown_only_doc_id_raises(ingested_corpus: tuple[Path, Path], tmp_path: Path) -> None:
    _, processed = ingested_corpus
    with pytest.raises(IngestionError, match="unknown doc_id"):
        chunk_corpus(
            config=ChunkingConfig(),
            processed_dir=processed,
            chunked_dir=tmp_path / "out",
            only=["rfc-does-not-exist"],
        )


@pytest.mark.unit
def test_tampered_chunk_manifest_detected(
    ingested_corpus: tuple[Path, Path], tmp_path: Path
) -> None:
    _, processed = ingested_corpus
    chunked = tmp_path / "chunked"
    chunk_corpus(
        config=ChunkingConfig(),
        processed_dir=processed,
        chunked_dir=chunked,
    )
    target = chunked / CHUNK_MANIFEST_FILENAME
    payload = target.read_text(encoding="utf-8")
    tampered = payload.replace('"corpus_version": "vtest"', '"corpus_version": "vEVIL"')
    target.write_text(tampered, encoding="utf-8")
    with pytest.raises(IngestionError, match="hash mismatch"):
        read_chunk_manifest(chunked)


@pytest.mark.unit
def test_missing_document_json_raises(tmp_path: Path) -> None:
    """If a manifest entry references a doc whose document.json is missing,
    chunking aborts with a clear error rather than silently producing an
    incomplete chunk_manifest."""
    processed = tmp_path / "processed"
    processed.mkdir()
    write_manifest(
        entries=[
            ManifestEntry(
                doc_id="rfc-missing",
                title="Missing",
                kind=SourceKind.RFC_TXT,
                source_url="https://x",
                license=License.PUBLIC_DOMAIN,
                sha256="a" * 64,
                fetched_at=datetime.now(UTC),
                n_sections=3,
                n_chars=100,
                raw_path=Path("/tmp/x.txt"),
                processed_dir=processed / "rfc-missing",
            )
        ],
        corpus_version="v1",
        processed_dir=processed,
    )
    with pytest.raises(IngestionError, match=r"missing document\.json"):
        chunk_corpus(
            config=ChunkingConfig(),
            processed_dir=processed,
            chunked_dir=tmp_path / "out",
        )
