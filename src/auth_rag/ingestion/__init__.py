"""Corpus download, parsing, and normalization.

Public entry point: :func:`ingest`. Everything else is composable internals.
"""

from __future__ import annotations

from auth_rag.ingestion.corpus_config import CorpusConfig, load_corpus_config
from auth_rag.ingestion.manifest import read_manifest, write_manifest
from auth_rag.ingestion.models import (
    License,
    Manifest,
    ManifestEntry,
    ParsedDocument,
    Section,
    SourceKind,
    SourceSpec,
)
from auth_rag.ingestion.pipeline import ingest

__all__ = [
    "CorpusConfig",
    "License",
    "Manifest",
    "ManifestEntry",
    "ParsedDocument",
    "Section",
    "SourceKind",
    "SourceSpec",
    "ingest",
    "load_corpus_config",
    "read_manifest",
    "write_manifest",
]
