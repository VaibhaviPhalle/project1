"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from auth_rag.logging_config import reset_for_tests
from auth_rag.settings import reload_settings


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets a clean Settings cache and explicitly-set env.

    Tests that need env vars should set them via ``monkeypatch.setenv``.
    """
    for var in [
        "AUTH_RAG_ENV",
        "AUTH_RAG_LOG_LEVEL",
        "AUTH_RAG_LOG_FORMAT",
        "AUTH_RAG_GENERATION_PROVIDER",
        "GROQ_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
    ]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AUTH_RAG_ENV", "ci")
    reload_settings()
    reset_for_tests()
