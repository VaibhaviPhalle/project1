"""Ingestion orchestrator: download → parse → scrub → write manifest.

This is the **only** entry point that the CLI calls. Everything else
(downloader, parser, scrubber, manifest) is composed here.

Per-source flow:

  1. Download into ``data/raw/{doc_id}.<ext>`` (idempotent, hash-verified).
  2. Parse format-specific (RFC text only in this PR).
  3. Scrub each section's text (PII baseline).
  4. Persist scrubbed sections to ``data/processed/{doc_id}/sections/NNN.txt``
     plus a per-doc ``document.json`` with metadata + section index.
  5. Append a :class:`ManifestEntry`.

After all sources are processed, the manifest is written atomically. If
any source fails, the run aborts before manifest write — no partial
manifest is ever persisted.

Filtering:
    Pass ``only`` to ingest a subset (e.g. for a single-doc dev loop).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from auth_rag.exceptions import IngestionError
from auth_rag.ingestion.corpus_config import CorpusConfig
from auth_rag.ingestion.downloader import download_source
from auth_rag.ingestion.manifest import write_manifest
from auth_rag.ingestion.models import (
    Manifest,
    ManifestEntry,
    ParsedDocument,
    Section,
    SourceKind,
    SourceSpec,
)
from auth_rag.ingestion.rfc_parser import parse_rfc
from auth_rag.ingestion.scrubber import scrub
from auth_rag.logging_config import get_logger

log = get_logger(__name__)


def ingest(
    *,
    config: CorpusConfig,
    raw_dir: Path,
    processed_dir: Path,
    only: Sequence[str] | None = None,
) -> Manifest:
    """Run the full ingestion pipeline for ``config``.

    Args:
        config: parsed ``corpus.yaml``.
        raw_dir: where downloaded source bytes live (``data/raw``).
        processed_dir: where scrubbed/structured output lives
            (``data/processed``).
        only: if set, only ingest the given ``doc_id``s.

    Returns:
        The :class:`Manifest` that was written.
    """
    selected = _filter_sources(config.sources, only)
    log.info(
        "ingest.pipeline.start",
        corpus_version=config.corpus_version,
        n_sources=len(selected),
        only=list(only) if only else None,
    )

    entries: list[ManifestEntry] = []
    for spec in selected:
        entries.append(_ingest_one(spec, raw_dir=raw_dir, processed_dir=processed_dir))

    manifest = write_manifest(
        entries=entries,
        corpus_version=config.corpus_version,
        processed_dir=processed_dir,
    )
    log.info(
        "ingest.pipeline.done",
        corpus_version=config.corpus_version,
        n_entries=len(manifest.entries),
        manifest_sha256=manifest.manifest_sha256,
    )
    return manifest


def _filter_sources(
    sources: Iterable[SourceSpec], only: Sequence[str] | None
) -> tuple[SourceSpec, ...]:
    if only is None:
        return tuple(sources)
    wanted = set(only)
    selected = tuple(s for s in sources if s.doc_id in wanted)
    missing = wanted - {s.doc_id for s in selected}
    if missing:
        raise IngestionError(f"unknown doc_id(s) in --only: {sorted(missing)}")
    return selected


def _ingest_one(
    spec: SourceSpec,
    *,
    raw_dir: Path,
    processed_dir: Path,
) -> ManifestEntry:
    download = download_source(spec, raw_dir=raw_dir)
    parsed = _parse(spec, download.path)
    scrubbed = _scrub_document(parsed)
    out_dir = processed_dir / spec.doc_id
    _write_processed(scrubbed, out_dir)
    return ManifestEntry(
        doc_id=spec.doc_id,
        title=spec.title,
        kind=spec.kind,
        source_url=spec.source_url,
        license=spec.license,
        sha256=download.sha256,
        fetched_at=datetime.now(UTC),
        n_sections=len(scrubbed.sections),
        n_chars=sum(len(s.text) for s in scrubbed.sections),
        raw_path=download.path,
        processed_dir=out_dir,
    )


def _parse(spec: SourceSpec, raw_path: Path) -> ParsedDocument:
    if spec.kind is SourceKind.RFC_TXT:
        return parse_rfc(spec, raw_path)
    raise IngestionError(
        f"no parser registered for kind={spec.kind} (doc_id={spec.doc_id}). "
        "HTML/Markdown loaders land in a follow-up PR."
    )


def _scrub_document(doc: ParsedDocument) -> ParsedDocument:
    """Return a copy of ``doc`` with every section's text scrubbed."""
    new_sections = tuple(
        Section(
            section_id=s.section_id,
            number=s.number,
            title=s.title,
            text=scrub(s.text),
            page_start=s.page_start,
            page_end=s.page_end,
            char_start=s.char_start,
            char_end=s.char_end,
            parent_section_id=s.parent_section_id,
        )
        for s in doc.sections
    )
    return ParsedDocument(
        doc_id=doc.doc_id,
        title=doc.title,
        kind=doc.kind,
        source_url=doc.source_url,
        license=doc.license,
        sha256=doc.sha256,
        fetched_at=doc.fetched_at,
        sections=new_sections,
        raw_char_count=doc.raw_char_count,
        metadata=doc.metadata,
    )


def _write_processed(doc: ParsedDocument, out_dir: Path) -> None:
    sections_dir = out_dir / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)
    for idx, section in enumerate(doc.sections):
        path = sections_dir / f"{idx:04d}_{section.section_id}.txt"
        path.write_text(section.text + "\n", encoding="utf-8")
    document_json = out_dir / "document.json"
    tmp = document_json.with_suffix(".json.part")
    tmp.write_text(
        doc.model_dump_json(indent=2, exclude_none=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(document_json)
