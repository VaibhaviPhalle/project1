"""Top-level package tests."""

from __future__ import annotations

import pytest

import auth_rag


@pytest.mark.unit
def test_version_is_string() -> None:
    assert isinstance(auth_rag.__version__, str)
    assert auth_rag.__version__.count(".") >= 2


@pytest.mark.unit
def test_public_api_exports_exceptions() -> None:
    assert hasattr(auth_rag, "AuthRAGError")
    assert hasattr(auth_rag, "ConfigError")
    assert hasattr(auth_rag, "RetrievalError")
    assert hasattr(auth_rag, "GenerationError")
    assert hasattr(auth_rag, "IngestionError")
