"""Chunking orchestrator: ingestion manifest → chunked corpus.

For every entry in ``data/processed/manifest.json``:

  1. Load the corresponding ``document.json`` written by ingestion.
  2. Chunk it via :func:`auth_rag.chunking.section_aware.chunk_document`.
  3. Write ``data/chunked/<doc_id>/chunks.jsonl`` (one JSON per line).
  4. Record a :class:`ChunkManifestEntry`.

After every doc is processed, write a single ``chunk_manifest.json`` whose
``chunk_manifest_sha256`` covers the chunking config + every chunk's id.
Step 4 keys the ChromaDB collection name on this hash so the index
rebuilds whenever any input changes.

If any per-doc step fails the run aborts before manifest write — no partial
chunk_manifest is ever persisted.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from auth_rag.chunking.models import (
    Chunk,
    ChunkingConfig,
    ChunkManifest,
    ChunkManifestEntry,
)
from auth_rag.chunking.section_aware import chunk_document
from auth_rag.exceptions import IngestionError
from auth_rag.ingestion.manifest import read_manifest
from auth_rag.ingestion.models import ManifestEntry, ParsedDocument
from auth_rag.logging_config import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

log = get_logger(__name__)

CHUNK_MANIFEST_FILENAME = "chunk_manifest.json"
CHUNKS_FILENAME = "chunks.jsonl"


def chunk_corpus(
    *,
    config: ChunkingConfig,
    processed_dir: Path,
    chunked_dir: Path,
    only: Sequence[str] | None = None,
) -> ChunkManifest:
    """Chunk every doc in the ingestion manifest under ``processed_dir``.

    Args:
        config: chunking parameters.
        processed_dir: where ``manifest.json`` + per-doc ``document.json``
            files live (output of Step 2).
        chunked_dir: output root. Per-doc subdirs hold the chunks files.
        only: restrict to these doc_ids.

    Returns:
        The :class:`ChunkManifest` that was written.
    """
    source_manifest = read_manifest(processed_dir)
    selected = _filter_entries(source_manifest.entries, only)
    log.info(
        "chunk.pipeline.start",
        corpus_version=source_manifest.corpus_version,
        n_docs=len(selected),
        chunk_size_tokens=config.chunk_size_tokens,
        chunk_overlap_tokens=config.chunk_overlap_tokens,
    )

    entries: list[ChunkManifestEntry] = []
    chunked_dir.mkdir(parents=True, exist_ok=True)
    for entry in selected:
        doc = _load_parsed_document(processed_dir, entry.doc_id)
        chunks = chunk_document(doc, config)
        if not chunks:
            raise IngestionError(f"chunker produced 0 chunks for {entry.doc_id}")
        chunks_path = chunked_dir / entry.doc_id / CHUNKS_FILENAME
        _write_chunks(chunks, chunks_path)
        entries.append(
            ChunkManifestEntry(
                doc_id=entry.doc_id,
                n_chunks=len(chunks),
                n_tokens_total=sum(c.n_tokens for c in chunks),
                chunks_path=chunks_path,
            )
        )
        log.info(
            "chunk.doc.done",
            doc_id=entry.doc_id,
            n_chunks=len(chunks),
            n_tokens_total=entries[-1].n_tokens_total,
        )

    manifest = _build_chunk_manifest(
        corpus_version=source_manifest.corpus_version,
        config=config,
        source_manifest_sha256=source_manifest.manifest_sha256,
        entries=entries,
    )
    _write_chunk_manifest(manifest, chunked_dir)
    log.info(
        "chunk.pipeline.done",
        n_docs=len(manifest.entries),
        chunk_manifest_sha256=manifest.chunk_manifest_sha256,
    )
    return manifest


def _filter_entries(
    entries: tuple[ManifestEntry, ...], only: Sequence[str] | None
) -> tuple[ManifestEntry, ...]:
    if only is None:
        return entries
    wanted = set(only)
    selected = tuple(e for e in entries if e.doc_id in wanted)
    missing = wanted - {e.doc_id for e in selected}
    if missing:
        raise IngestionError(f"unknown doc_id(s) in --only: {sorted(missing)}")
    return selected


def _load_parsed_document(processed_dir: Path, doc_id: str) -> ParsedDocument:
    path = processed_dir / doc_id / "document.json"
    if not path.is_file():
        raise IngestionError(f"missing document.json for {doc_id}: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ParsedDocument.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise IngestionError(f"invalid document.json for {doc_id}: {path}") from exc


def _write_chunks(chunks: Iterable[Chunk], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with tmp.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(chunk.model_dump_json(exclude_none=True))
            f.write("\n")
    tmp.replace(path)


def read_chunks(path: Path) -> list[Chunk]:
    """Read a JSONL file written by :func:`_write_chunks`."""
    if not path.is_file():
        raise IngestionError(f"chunks file not found: {path}")
    out: list[Chunk] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                out.append(Chunk.model_validate_json(line))
            except ValidationError as exc:
                raise IngestionError(f"invalid chunk in {path}:{line_no}") from exc
    return out


def _build_chunk_manifest(
    *,
    corpus_version: str,
    config: ChunkingConfig,
    source_manifest_sha256: str,
    entries: list[ChunkManifestEntry],
) -> ChunkManifest:
    sorted_entries = tuple(sorted(entries, key=lambda e: e.doc_id))
    canonical = _canonical_blob(
        corpus_version=corpus_version,
        config=config,
        source_manifest_sha256=source_manifest_sha256,
        entries=sorted_entries,
    )
    chunk_manifest_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return ChunkManifest(
        corpus_version=corpus_version,
        chunking_config=config,
        source_manifest_sha256=source_manifest_sha256,
        generated_at=datetime.now(UTC),
        entries=sorted_entries,
        chunk_manifest_sha256=chunk_manifest_sha256,
    )


def _canonical_blob(
    *,
    corpus_version: str,
    config: ChunkingConfig,
    source_manifest_sha256: str,
    entries: tuple[ChunkManifestEntry, ...],
) -> str:
    payload = {
        "corpus_version": corpus_version,
        "config": json.loads(config.model_dump_json()),
        "source_manifest_sha256": source_manifest_sha256,
        # Exclude chunks_path: it's a deployment-local artifact that varies
        # between checkouts/containers. Hash should depend only on content.
        "entries": [
            json.loads(e.model_dump_json(exclude={"chunks_path"}, exclude_none=True))
            for e in entries
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _write_chunk_manifest(manifest: ChunkManifest, chunked_dir: Path) -> None:
    target = chunked_dir / CHUNK_MANIFEST_FILENAME
    tmp = target.with_suffix(".json.part")
    tmp.write_text(
        manifest.model_dump_json(indent=2, exclude_none=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(target)


def read_chunk_manifest(chunked_dir: Path) -> ChunkManifest:
    """Load and verify the chunk manifest under ``chunked_dir``."""
    target = chunked_dir / CHUNK_MANIFEST_FILENAME
    if not target.is_file():
        raise IngestionError(f"chunk manifest not found: {target}")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        manifest = ChunkManifest.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise IngestionError(f"chunk manifest is invalid: {target}") from exc

    canonical = _canonical_blob(
        corpus_version=manifest.corpus_version,
        config=manifest.chunking_config,
        source_manifest_sha256=manifest.source_manifest_sha256,
        entries=manifest.entries,
    )
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if expected != manifest.chunk_manifest_sha256:
        raise IngestionError(
            f"chunk manifest hash mismatch: stored={manifest.chunk_manifest_sha256} "
            f"recomputed={expected}"
        )
    return manifest
