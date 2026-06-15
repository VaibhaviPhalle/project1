"""Loader for ``config/corpus.yaml``.

Single function: :func:`load_corpus_config`. Returns a validated
:class:`CorpusConfig` (corpus version + tuple of :class:`SourceSpec`).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from auth_rag.exceptions import ConfigError
from auth_rag.ingestion.models import SourceSpec


class CorpusConfig(BaseModel):
    """Top-level shape of ``config/corpus.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    corpus_version: str = Field(min_length=1)
    sources: tuple[SourceSpec, ...] = Field(min_length=1)


def load_corpus_config(path: Path) -> CorpusConfig:
    """Load and validate the corpus YAML.

    Raises:
        ConfigError: if the file is missing, malformed, or fails validation.
    """
    if not path.is_file():
        raise ConfigError(f"corpus config not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"corpus config is not valid YAML: {path}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"corpus config must be a mapping: {path}")

    _check_unique_doc_ids(raw.get("sources") or [])

    try:
        return CorpusConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"corpus config validation failed: {exc}") from exc


def _check_unique_doc_ids(sources: list[dict[str, object]]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for entry in sources:
        if not isinstance(entry, dict):
            continue
        doc_id = entry.get("doc_id")
        if not isinstance(doc_id, str):
            continue
        if doc_id in seen:
            duplicates.add(doc_id)
        seen.add(doc_id)
    if duplicates:
        raise ConfigError(f"corpus config has duplicate doc_id(s): {sorted(duplicates)}")
