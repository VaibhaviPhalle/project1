"""Pydantic models for the ingestion stage.

Every data structure that crosses an ingestion module boundary is one of these
types. The rest of the pipeline (chunking, retrieval, generation) only ever
sees ``ParsedDocument`` and ``Manifest`` — never raw strings or dicts.

Design notes:
    * Models are ``frozen`` so they're hashable and safe to share across threads.
    * ``Section`` carries everything needed to render a citation:
      ``[doc_id §section_number p.page]``.
    * ``Manifest`` is the single source of truth for what's in the corpus —
      every later stage must consult it (see ADR 0006 layer 3).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceKind(StrEnum):
    """Format of a source document. Determines which loader handles it."""

    RFC_TXT = "rfc_txt"
    MARKDOWN = "markdown"
    HTML = "html"


class License(StrEnum):
    """License of a source document. Recorded so attribution stays honest.

    Values map to SPDX identifiers where they exist, plus a few specific
    public-policy markers (RFCs, OASIS) that don't have SPDX equivalents.
    """

    PUBLIC_DOMAIN = "public-domain"  # IETF RFCs (BCP 78)
    APACHE_2_0 = "Apache-2.0"
    MIT = "MIT"
    CC_BY_4_0 = "CC-BY-4.0"
    OASIS_IPR = "OASIS-IPR"  # SAML, etc.
    OPENID_FOUNDATION = "OpenID-Foundation"
    PROPRIETARY_PUBLIC = (
        "proprietary-public"  # vendor docs that allow reading + citation but not redistribution
    )


class SourceSpec(BaseModel):
    """Declarative spec for one source document.

    Loaded from ``config/corpus.yaml``; one entry per document. The set of
    specs is the contract between corpus authors and the ingestion pipeline.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    doc_id: str = Field(min_length=1, pattern=r"^[a-z0-9_\-]+$")
    title: str = Field(min_length=1)
    kind: SourceKind
    source_url: str = Field(min_length=1)
    license: License
    expected_sha256: str | None = Field(
        default=None,
        description="If set, the downloader rejects content with a different hash.",
        pattern=r"^[a-f0-9]{64}$",
    )
    notes: str | None = None


class Section(BaseModel):
    """One logical section of a parsed document.

    For RFCs, sections are derived from the canonical numbered structure
    (``4.1.1 Authorization Code Grant``). For Markdown, they come from
    heading hierarchy. The pipeline never splits across sections; this is
    the citation atom.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    section_id: str = Field(min_length=1, description="Stable id within the document.")
    number: str | None = Field(
        default=None,
        description="Hierarchical number (e.g. '4.1.1'). None for unnumbered sections.",
    )
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    char_start: int = Field(ge=0, description="Byte offset within the source's raw text.")
    char_end: int = Field(ge=0)
    parent_section_id: str | None = None


class ParsedDocument(BaseModel):
    """A source document after parsing — purely in-memory representation.

    The persisted form is the manifest entry plus on-disk text files (one
    per section) under ``data/processed/{doc_id}/``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    doc_id: str
    title: str
    kind: SourceKind
    source_url: str
    license: License
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    fetched_at: datetime
    sections: tuple[Section, ...]
    raw_char_count: int = Field(ge=0)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("sections")
    @classmethod
    def _at_least_one_section(cls, value: tuple[Section, ...]) -> tuple[Section, ...]:
        if not value:
            raise ValueError("ParsedDocument requires at least one section")
        return value


class ManifestEntry(BaseModel):
    """One row of the corpus manifest. Persisted to ``manifest.json``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    doc_id: str
    title: str
    kind: SourceKind
    source_url: str
    license: License
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    fetched_at: datetime
    n_sections: int = Field(ge=1)
    n_chars: int = Field(ge=0)
    raw_path: Path
    processed_dir: Path


class Manifest(BaseModel):
    """The corpus manifest — the canonical list of what's been ingested.

    Includes a ``manifest_sha256`` (hash of the canonical JSON of all entries)
    so downstream stages can detect if the corpus has changed without
    re-reading every file.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    corpus_version: str = Field(min_length=1)
    generated_at: datetime
    entries: tuple[ManifestEntry, ...]
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
