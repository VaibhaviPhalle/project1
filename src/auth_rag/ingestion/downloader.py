"""HTTP downloader for corpus sources.

Design:
    * **Atomic writes.** Stream to a ``.part`` file, fsync, then rename. A
      crashed run never leaves a half-written file that the parser would
      mistakenly accept.
    * **Hash verification.** If ``expected_sha256`` is set on the spec, the
      downloader rejects any payload whose hash differs (raises
      :class:`CorpusIntegrityError`).
    * **Idempotent.** A second run with a matching on-disk hash is a no-op.
    * **Retries with backoff.** Transient network errors retry up to four
      times via :mod:`tenacity` with exponential backoff.
    * **Offline kill switch.** If ``AUTH_RAG_OFFLINE=1`` is set, the
      downloader refuses any HTTP call and raises immediately. Default in CI.
    * **Size cap.** Each download is bounded so a misconfigured URL can't
      fill the disk.

The downloader writes a sidecar ``<file>.meta.json`` next to each artifact:
``{url, fetched_at, sha256, content_length}``. Subsequent runs use it to
skip work without re-hashing the file.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from auth_rag.exceptions import CorpusIntegrityError, IngestionError
from auth_rag.ingestion.models import SourceKind
from auth_rag.logging_config import get_logger

if TYPE_CHECKING:
    from auth_rag.ingestion.models import SourceSpec

log = get_logger(__name__)

_DEFAULT_TIMEOUT_S = 30.0
_DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB hard cap per file
_CHUNK_BYTES = 64 * 1024
_USER_AGENT = "auth-rag/0.1 (+https://github.com/auth-rag)"


class DownloadResult:
    """Outcome of a single download. Lightweight value object."""

    __slots__ = ("from_cache", "n_bytes", "path", "sha256")

    def __init__(self, *, path: Path, sha256: str, from_cache: bool, n_bytes: int) -> None:
        self.path = path
        self.sha256 = sha256
        self.from_cache = from_cache
        self.n_bytes = n_bytes


def _is_offline() -> bool:
    return os.environ.get("AUTH_RAG_OFFLINE", "").strip() in {"1", "true", "True"}


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK_BYTES):
            h.update(chunk)
    return h.hexdigest()


def _meta_path(target: Path) -> Path:
    return target.with_suffix(target.suffix + ".meta.json")


def _read_cached_hash(target: Path) -> str | None:
    """Return the cached sha256 if both the file and its sidecar exist."""
    meta = _meta_path(target)
    if not (target.is_file() and meta.is_file()):
        return None
    try:
        payload = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    cached = payload.get("sha256")
    return cached if isinstance(cached, str) else None


def _write_meta(target: Path, *, url: str, sha256: str, n_bytes: int) -> None:
    meta = _meta_path(target)
    meta.write_text(
        json.dumps(
            {
                "url": url,
                "fetched_at": datetime.now(UTC).isoformat(),
                "sha256": sha256,
                "content_length": n_bytes,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


@retry(
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=32),
    reraise=True,
)
def _stream_to_part(
    *,
    url: str,
    part: Path,
    timeout_s: float,
    max_bytes: int,
) -> tuple[str, int]:
    """Stream ``url`` to ``part``; return (sha256, n_bytes). Caller renames."""
    h = hashlib.sha256()
    n_bytes = 0
    headers = {"User-Agent": _USER_AGENT, "Accept": "*/*"}
    with (
        httpx.Client(timeout=timeout_s, follow_redirects=True, headers=headers) as client,
        client.stream("GET", url) as response,
    ):
        response.raise_for_status()
        with part.open("wb") as f:
            for chunk in response.iter_bytes(chunk_size=_CHUNK_BYTES):
                if not chunk:
                    continue
                n_bytes += len(chunk)
                if n_bytes > max_bytes:
                    raise IngestionError(f"download exceeded {max_bytes} byte cap: {url}")
                h.update(chunk)
                f.write(chunk)
            f.flush()
            os.fsync(f.fileno())
    return h.hexdigest(), n_bytes


def download_source(
    spec: SourceSpec,
    *,
    raw_dir: Path,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> DownloadResult:
    """Fetch a single :class:`SourceSpec` into ``raw_dir/{doc_id}.<ext>``.

    Returns a :class:`DownloadResult` with the resolved hash and a
    ``from_cache`` flag indicating whether bytes were re-fetched.

    Raises:
        IngestionError: on offline-mode violation, transport failure after
            retries, or oversize content.
        CorpusIntegrityError: when ``expected_sha256`` is set and the fetched
            content's hash does not match.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    extension = _extension_for(spec)
    target = raw_dir / f"{spec.doc_id}{extension}"

    cached = _read_cached_hash(target)
    if cached is not None:
        if spec.expected_sha256 is not None and cached != spec.expected_sha256:
            raise CorpusIntegrityError(
                f"cached file for {spec.doc_id} has sha256={cached} "
                f"but expected={spec.expected_sha256}"
            )
        log.info(
            "ingest.download.cache_hit",
            doc_id=spec.doc_id,
            sha256=cached,
            path=str(target),
        )
        return DownloadResult(
            path=target,
            sha256=cached,
            from_cache=True,
            n_bytes=target.stat().st_size,
        )

    if _is_offline():
        raise IngestionError(f"AUTH_RAG_OFFLINE=1 but no cached copy of {spec.doc_id} at {target}")

    log.info("ingest.download.start", doc_id=spec.doc_id, url=spec.source_url)
    part = target.with_suffix(target.suffix + ".part")
    try:
        sha256, n_bytes = _stream_to_part(
            url=spec.source_url,
            part=part,
            timeout_s=timeout_s,
            max_bytes=max_bytes,
        )
    except httpx.HTTPError as exc:
        if part.exists():
            part.unlink(missing_ok=True)
        raise IngestionError(f"download failed for {spec.doc_id}: {exc}") from exc

    if spec.expected_sha256 is not None and sha256 != spec.expected_sha256:
        part.unlink(missing_ok=True)
        raise CorpusIntegrityError(
            f"sha256 mismatch for {spec.doc_id}: got {sha256}, expected {spec.expected_sha256}"
        )

    part.replace(target)
    _write_meta(target, url=spec.source_url, sha256=sha256, n_bytes=n_bytes)
    log.info(
        "ingest.download.done",
        doc_id=spec.doc_id,
        sha256=sha256,
        n_bytes=n_bytes,
        path=str(target),
    )
    return DownloadResult(path=target, sha256=sha256, from_cache=False, n_bytes=n_bytes)


_EXTENSION_BY_KIND = {
    SourceKind.RFC_TXT: ".txt",
    SourceKind.MARKDOWN: ".md",
    SourceKind.HTML: ".html",
}


def _extension_for(spec: SourceSpec) -> str:
    """Map :class:`SourceKind` to a file extension."""
    return _EXTENSION_BY_KIND[spec.kind]
