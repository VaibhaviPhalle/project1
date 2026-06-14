"""Tests for structured logging configuration."""

from __future__ import annotations

import json

import pytest

from auth_rag.logging_config import (
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
    reset_for_tests,
)
from auth_rag.settings import LogFormat


@pytest.mark.unit
def test_console_logging_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    reset_for_tests()
    configure_logging(level="INFO", fmt=LogFormat.CONSOLE)
    log = get_logger("test")
    log.info("hello", k="v")
    out = capsys.readouterr().out
    assert "hello" in out
    assert "k" in out


@pytest.mark.unit
def test_json_logging_emits_valid_json(capsys: pytest.CaptureFixture[str]) -> None:
    reset_for_tests()
    configure_logging(level="INFO", fmt=LogFormat.JSON)
    log = get_logger("test")
    log.info("event", foo=1, bar="baz")
    out = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(out)
    assert payload["event"] == "event"
    assert payload["foo"] == 1
    assert payload["bar"] == "baz"
    assert payload["level"] == "info"


@pytest.mark.unit
def test_context_vars_propagate(capsys: pytest.CaptureFixture[str]) -> None:
    reset_for_tests()
    configure_logging(level="INFO", fmt=LogFormat.JSON)
    log = get_logger("test")
    bind_context(request_id="req-123")
    try:
        log.info("processed")
    finally:
        clear_context()
    out = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(out)
    assert payload["request_id"] == "req-123"


@pytest.mark.unit
def test_configure_is_idempotent() -> None:
    reset_for_tests()
    configure_logging(level="INFO", fmt=LogFormat.JSON)
    configure_logging(level="DEBUG", fmt=LogFormat.CONSOLE)
    log = get_logger("test")
    assert log is not None
