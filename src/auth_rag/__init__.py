"""Auth-RAG: Retrieval-augmented QA over auth/identity protocols.

Public API kept intentionally minimal. Compose deeper pieces from submodules.
"""

from __future__ import annotations

from auth_rag._version import __version__
from auth_rag.exceptions import (
    AuthRAGError,
    ConfigError,
    GenerationError,
    IngestionError,
    RetrievalError,
)

__all__ = [
    "AuthRAGError",
    "ConfigError",
    "GenerationError",
    "IngestionError",
    "RetrievalError",
    "__version__",
]
