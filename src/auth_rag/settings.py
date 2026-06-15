"""Application settings.

Single source of truth for runtime configuration. Reads from environment
variables (prefix ``AUTH_RAG_``) and ``.env`` files. Secrets are wrapped in
``SecretStr`` so they don't leak into logs via ``repr``.

Why pydantic-settings (and not Hydra):
    - Type-safe access throughout the codebase.
    - Validation at startup (fail fast, never run with a bad config).
    - First-class secret handling.

Hydra-style YAML *content* configuration (prompts, retrieval params, etc.)
lives under ``config/`` and is loaded separately via :mod:`auth_rag.config`.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from auth_rag.exceptions import ConfigError

# Repo root: settings.py is at src/auth_rag/settings.py, so parents[2] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Environment(StrEnum):
    """Runtime environment. Drives logging format and safety defaults."""

    LOCAL = "local"
    CI = "ci"
    PROD = "prod"


class LogFormat(StrEnum):
    CONSOLE = "console"
    JSON = "json"


class GenerationProvider(StrEnum):
    GROQ = "groq"
    GOOGLE = "google"
    OLLAMA = "ollama"
    OPENAI = "openai"


class Settings(BaseSettings):
    """Top-level settings object. Instantiate via :func:`get_settings`."""

    model_config = SettingsConfigDict(
        env_prefix="AUTH_RAG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Runtime ----
    env: Environment = Environment.LOCAL
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.CONSOLE

    # ---- Paths (resolved against repo root if relative) ----
    data_dir: Path = Field(default=Path("data"))
    index_dir: Path = Field(default=Path("chroma_db"))
    cache_dir: Path = Field(default=Path(".cache"))

    # ---- Models ----
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "BAAI/bge-reranker-base"
    generation_provider: GenerationProvider = GenerationProvider.GROQ
    generation_model: str = "llama-3.3-70b-versatile"

    # ---- Provider keys (loaded from non-prefixed names; see validators below) ----
    groq_api_key: SecretStr | None = Field(default=None, alias="GROQ_API_KEY")
    google_api_key: SecretStr | None = Field(default=None, alias="GOOGLE_API_KEY")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    langsmith_api_key: SecretStr | None = Field(default=None, alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="auth-rag", alias="LANGSMITH_PROJECT")

    @field_validator("data_dir", "index_dir", "cache_dir", mode="after")
    @classmethod
    def _resolve_path(cls, value: Path) -> Path:
        """Resolve relative paths against the repo root for stability across CWDs."""
        return value if value.is_absolute() else (_REPO_ROOT / value).resolve()

    @field_validator("log_level", mode="after")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError(f"Invalid log level: {value!r}")
        return normalized

    # ---- Convenience ----
    def repo_root(self) -> Path:
        return _REPO_ROOT

    def require_provider_key(self) -> SecretStr:
        """Return the API key required by the configured ``generation_provider``.

        Raises ``ConfigError`` if missing. Ollama needs no key.
        """
        match self.generation_provider:
            case GenerationProvider.GROQ:
                if self.groq_api_key is None:
                    raise ConfigError("GROQ_API_KEY is required for provider=groq")
                return self.groq_api_key
            case GenerationProvider.GOOGLE:
                if self.google_api_key is None:
                    raise ConfigError("GOOGLE_API_KEY is required for provider=google")
                return self.google_api_key
            case GenerationProvider.OPENAI:
                if self.openai_api_key is None:
                    raise ConfigError("OPENAI_API_KEY is required for provider=openai")
                return self.openai_api_key
            case GenerationProvider.OLLAMA:
                # Ollama runs locally; no key needed but return an empty SecretStr
                # so call sites have a uniform return type.
                return SecretStr("")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor.

    Use this everywhere instead of instantiating ``Settings()`` directly so
    the ``.env`` is loaded exactly once per process.
    """
    return Settings()


def reload_settings() -> Settings:
    """Force-reload settings (test helper)."""
    get_settings.cache_clear()
    return get_settings()
