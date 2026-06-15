"""Tests for :mod:`auth_rag.settings`."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from auth_rag.exceptions import ConfigError
from auth_rag.settings import (
    Environment,
    GenerationProvider,
    LogFormat,
    reload_settings,
)


@pytest.mark.unit
def test_defaults_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_RAG_ENV", "local")
    s = reload_settings()
    assert s.env is Environment.LOCAL
    assert s.log_format is LogFormat.CONSOLE
    assert s.embedding_model.startswith("BAAI/bge")
    assert s.data_dir.is_absolute()


@pytest.mark.unit
def test_invalid_log_level_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_RAG_LOG_LEVEL", "TRACE")
    with pytest.raises((ConfigError, ValidationError), match="Invalid log level"):
        reload_settings()


@pytest.mark.unit
def test_secret_redacted_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "supersecret")
    s = reload_settings()
    assert isinstance(s.groq_api_key, SecretStr)
    assert "supersecret" not in repr(s)


@pytest.mark.unit
def test_require_provider_key_groq_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_RAG_GENERATION_PROVIDER", "groq")
    s = reload_settings()
    with pytest.raises(ConfigError, match="GROQ_API_KEY"):
        s.require_provider_key()


@pytest.mark.unit
def test_require_provider_key_groq_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_RAG_GENERATION_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    s = reload_settings()
    key = s.require_provider_key()
    assert key.get_secret_value() == "k"


@pytest.mark.unit
def test_ollama_needs_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_RAG_GENERATION_PROVIDER", "ollama")
    s = reload_settings()
    assert s.generation_provider is GenerationProvider.OLLAMA
    assert s.require_provider_key().get_secret_value() == ""


@pytest.mark.unit
def test_relative_paths_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_RAG_DATA_DIR", "data")
    s = reload_settings()
    assert s.data_dir.is_absolute()
    assert s.data_dir.name == "data"
