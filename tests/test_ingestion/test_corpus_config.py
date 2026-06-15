"""Tests for corpus.yaml loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from auth_rag.exceptions import ConfigError
from auth_rag.ingestion.corpus_config import load_corpus_config

_VALID_YAML = """
corpus_version: "v1"
sources:
  - doc_id: rfc6749
    title: "OAuth 2.0"
    kind: rfc_txt
    source_url: "https://example.com/rfc6749.txt"
    license: public-domain
"""


@pytest.mark.unit
def test_load_valid_yaml(tmp_path: Path) -> None:
    p = tmp_path / "corpus.yaml"
    p.write_text(_VALID_YAML, encoding="utf-8")
    config = load_corpus_config(p)
    assert config.corpus_version == "v1"
    assert len(config.sources) == 1
    assert config.sources[0].doc_id == "rfc6749"


@pytest.mark.unit
def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_corpus_config(tmp_path / "nope.yaml")


@pytest.mark.unit
def test_malformed_yaml_raises(tmp_path: Path) -> None:
    p = tmp_path / "corpus.yaml"
    p.write_text(":\n  - oops: [\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_corpus_config(p)


@pytest.mark.unit
def test_duplicate_doc_ids_rejected(tmp_path: Path) -> None:
    yaml = """
corpus_version: "v1"
sources:
  - doc_id: rfc6749
    title: "A"
    kind: rfc_txt
    source_url: "https://x/a.txt"
    license: public-domain
  - doc_id: rfc6749
    title: "B"
    kind: rfc_txt
    source_url: "https://x/b.txt"
    license: public-domain
"""
    p = tmp_path / "corpus.yaml"
    p.write_text(yaml, encoding="utf-8")
    with pytest.raises(ConfigError, match="duplicate"):
        load_corpus_config(p)


@pytest.mark.unit
def test_empty_sources_rejected(tmp_path: Path) -> None:
    p = tmp_path / "corpus.yaml"
    p.write_text('corpus_version: "v1"\nsources: []\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_corpus_config(p)


@pytest.mark.unit
def test_real_corpus_yaml_loads() -> None:
    """The committed config/corpus.yaml is itself valid."""
    repo_root = Path(__file__).resolve().parents[2]
    config = load_corpus_config(repo_root / "config" / "corpus.yaml")
    assert config.corpus_version == "v1"
    assert len(config.sources) >= 10  # all the RFCs we declared
    doc_ids = {s.doc_id for s in config.sources}
    for must_have in ("rfc6749", "rfc7519", "rfc7636", "rfc8252"):
        assert must_have in doc_ids
