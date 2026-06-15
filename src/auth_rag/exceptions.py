"""Exception hierarchy for auth-rag.

A typed hierarchy lets callers catch specific failure modes instead of bare
``except``. Every component raises one of these (never a stdlib exception
directly across module boundaries).
"""

from __future__ import annotations


class AuthRAGError(Exception):
    """Base class for all auth-rag errors."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
class ConfigError(AuthRAGError):
    """Invalid or missing configuration."""


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------
class IngestionError(AuthRAGError):
    """Failure during corpus download, parsing, or normalization."""


class CorpusIntegrityError(IngestionError):
    """A source document failed an integrity check (hash mismatch, truncated)."""


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
class RetrievalError(AuthRAGError):
    """Failure during retrieval (vector, sparse, or hybrid)."""


class EmptyRetrievalError(RetrievalError):
    """No chunks were retrieved (or all fell below the relevance threshold).

    Callers should typically convert this to an ``insufficient context``
    response rather than calling the LLM.
    """


class IndexCorruptError(RetrievalError):
    """The vector or sparse index is missing or in an inconsistent state."""


class EmbeddingDimensionMismatchError(RetrievalError):
    """The loaded embedding model produces vectors of a different dimension
    than the index was built with. Refuse to proceed rather than silently
    return garbage.
    """


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
class GenerationError(AuthRAGError):
    """Failure during LLM generation."""


class LLMTimeoutError(GenerationError):
    """The LLM provider did not respond within the configured timeout."""


class LLMRateLimitError(GenerationError):
    """The LLM provider returned a rate-limit / quota error."""


class LLMOutputInvalidError(GenerationError):
    """The LLM returned output that could not be parsed against the expected
    schema after the configured number of repair attempts.
    """


# ---------------------------------------------------------------------------
# Verification (citation / faithfulness guardrails)
# ---------------------------------------------------------------------------
class VerificationError(AuthRAGError):
    """Citation or faithfulness verification failed."""


class CitationMissingError(VerificationError):
    """The generated answer makes claims that are not accompanied by citations."""


class CitationUnsupportedError(VerificationError):
    """A citation references a chunk that does not entail the cited claim."""


class CitationNotFoundError(VerificationError):
    """A citation references a doc/section that does not exist in the corpus
    (the model hallucinated a citation).
    """
