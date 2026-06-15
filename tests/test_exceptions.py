"""Tests for the exception hierarchy."""

from __future__ import annotations

import pytest

from auth_rag.exceptions import (
    AuthRAGError,
    CitationMissingError,
    CitationNotFoundError,
    CitationUnsupportedError,
    ConfigError,
    CorpusIntegrityError,
    EmbeddingDimensionMismatchError,
    EmptyRetrievalError,
    GenerationError,
    IndexCorruptError,
    IngestionError,
    LLMOutputInvalidError,
    LLMRateLimitError,
    LLMTimeoutError,
    RetrievalError,
    VerificationError,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "exc_cls",
    [
        ConfigError,
        IngestionError,
        CorpusIntegrityError,
        RetrievalError,
        EmptyRetrievalError,
        IndexCorruptError,
        EmbeddingDimensionMismatchError,
        GenerationError,
        LLMTimeoutError,
        LLMRateLimitError,
        LLMOutputInvalidError,
        VerificationError,
        CitationMissingError,
        CitationUnsupportedError,
        CitationNotFoundError,
    ],
)
def test_all_inherit_from_base(exc_cls: type[Exception]) -> None:
    assert issubclass(exc_cls, AuthRAGError)


@pytest.mark.unit
def test_specific_subclass_inheritance() -> None:
    assert issubclass(CorpusIntegrityError, IngestionError)
    assert issubclass(EmptyRetrievalError, RetrievalError)
    assert issubclass(LLMTimeoutError, GenerationError)
    assert issubclass(CitationMissingError, VerificationError)
