"""Smoke tests for the CLI entry point."""

from __future__ import annotations

import pytest

from auth_rag.cli import main


@pytest.mark.unit
def test_cli_no_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([])
    assert rc == 0
    assert "auth-rag" in capsys.readouterr().out


@pytest.mark.unit
def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "auth-rag" in capsys.readouterr().out


@pytest.mark.unit
def test_cli_info() -> None:
    rc = main(["info"])
    assert rc == 0


@pytest.mark.unit
def test_cli_unknown_command_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["does-not-exist"])
    assert exc.value.code != 0
