"""Structured logging setup.

Console renderer for local dev (human-readable), JSON renderer for CI/prod
(grep-able, ingestible by log backends). Every log line is enriched with
contextual fields via :func:`bind_context`.

Usage::

    from auth_rag.logging_config import configure_logging, get_logger
    configure_logging()
    log = get_logger(__name__)
    log.info("indexing.start", n_docs=42, corpus_version="v1")
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import structlog

from auth_rag.settings import LogFormat, get_settings

if TYPE_CHECKING:
    from structlog.types import Processor

_CONFIGURED = False


def configure_logging(
    *,
    level: str | None = None,
    fmt: LogFormat | None = None,
) -> None:
    """Idempotently configure stdlib + structlog.

    Safe to call multiple times; only the first call takes effect.
    """
    global _CONFIGURED  # noqa: PLW0603 - intentional one-shot guard
    if _CONFIGURED:
        return

    settings = get_settings()
    effective_level = (level or settings.log_level).upper()
    effective_fmt = fmt or settings.log_format

    # Bridge stdlib logging (chromadb, langchain, etc.) into our renderer.
    # ``force=True`` ensures repeated configuration in tests takes effect.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=effective_level,
        force=True,
    )

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Processor
    if effective_fmt is LogFormat.JSON:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(effective_level)),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger. Auto-configures on first call."""
    if not _CONFIGURED:
        configure_logging()
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


def bind_context(**kwargs: Any) -> None:
    """Bind context vars (e.g. ``request_id``) for the current async/thread context.

    Subsequent log calls in this context inherit these fields automatically.
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear all context vars for the current context."""
    structlog.contextvars.clear_contextvars()


def reset_for_tests() -> None:
    """Reset the one-shot guard (test helper). Not for production use."""
    global _CONFIGURED  # noqa: PLW0603
    _CONFIGURED = False
    structlog.reset_defaults()
