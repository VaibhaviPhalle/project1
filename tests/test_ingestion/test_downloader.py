"""Tests for the HTTP downloader.

All tests are offline — `httpx.MockTransport` simulates the network so CI
stays hermetic.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from auth_rag.exceptions import CorpusIntegrityError, IngestionError
from auth_rag.ingestion import downloader
from auth_rag.ingestion.models import License, SourceKind, SourceSpec


def _spec(*, expected_sha256: str | None = None) -> SourceSpec:
    return SourceSpec(
        doc_id="rfc9999",
        title="Sample",
        kind=SourceKind.RFC_TXT,
        source_url="https://example.com/rfc9999.txt",
        license=License.PUBLIC_DOMAIN,
        expected_sha256=expected_sha256,
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
def test_downloads_and_writes_meta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = b"hello rfc"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("rfc9999.txt")
        return httpx.Response(200, content=body)

    _install_transport(monkeypatch, handler)
    monkeypatch.delenv("AUTH_RAG_OFFLINE", raising=False)

    result = downloader.download_source(_spec(), raw_dir=tmp_path)
    assert result.path.read_bytes() == body
    assert result.sha256 == hashlib.sha256(body).hexdigest()
    assert not result.from_cache
    meta = result.path.with_suffix(result.path.suffix + ".meta.json")
    assert meta.is_file()


@pytest.mark.unit
def test_cache_hit_skips_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = b"cached content"
    sha = hashlib.sha256(body).hexdigest()

    target = tmp_path / "rfc9999.txt"
    target.write_bytes(body)
    meta = target.with_suffix(target.suffix + ".meta.json")
    meta.write_text(
        '{"url":"https://example.com/rfc9999.txt","fetched_at":"2026-01-01T00:00:00+00:00",'
        f'"sha256":"{sha}","content_length":{len(body)}}}',
        encoding="utf-8",
    )

    def fail(_: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be called on cache hit")

    _install_transport(monkeypatch, fail)
    monkeypatch.delenv("AUTH_RAG_OFFLINE", raising=False)

    result = downloader.download_source(_spec(), raw_dir=tmp_path)
    assert result.from_cache
    assert result.sha256 == sha


@pytest.mark.unit
def test_offline_mode_with_no_cache_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_RAG_OFFLINE", "1")
    with pytest.raises(IngestionError, match="OFFLINE"):
        downloader.download_source(_spec(), raw_dir=tmp_path)


@pytest.mark.unit
def test_hash_mismatch_rejects_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = b"unexpected"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    _install_transport(monkeypatch, handler)
    monkeypatch.delenv("AUTH_RAG_OFFLINE", raising=False)

    spec = _spec(expected_sha256="0" * 64)
    with pytest.raises(CorpusIntegrityError, match="sha256 mismatch"):
        downloader.download_source(spec, raw_dir=tmp_path)
    # The temp .part file must not be left behind.
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.unit
def test_size_cap_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = b"x" * 1024

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    _install_transport(monkeypatch, handler)
    monkeypatch.delenv("AUTH_RAG_OFFLINE", raising=False)

    with pytest.raises(IngestionError, match="cap"):
        downloader.download_source(_spec(), raw_dir=tmp_path, max_bytes=100)


@pytest.mark.unit
def test_http_error_raises_after_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    _install_transport(monkeypatch, handler)
    monkeypatch.delenv("AUTH_RAG_OFFLINE", raising=False)

    monkeypatch.setattr(downloader._stream_to_part.retry, "sleep", lambda _: None)

    with pytest.raises(IngestionError, match="download failed"):
        downloader.download_source(_spec(), raw_dir=tmp_path, timeout_s=1.0)
