"""Tests for the PII scrubber."""

from __future__ import annotations

import pytest

from auth_rag.ingestion.scrubber import (
    EMAIL_PLACEHOLDER,
    IP_PLACEHOLDER,
    has_pii,
    scrub,
)


@pytest.mark.unit
def test_scrubs_email() -> None:
    text = "Contact alice@example.com for details."
    out = scrub(text)
    assert "alice@example.com" not in out
    assert EMAIL_PLACEHOLDER in out


@pytest.mark.unit
def test_scrubs_ipv4_outside_doc_ranges() -> None:
    out = scrub("Server is at 10.0.0.5 today.")
    assert "10.0.0.5" not in out
    assert IP_PLACEHOLDER in out


@pytest.mark.unit
@pytest.mark.parametrize(
    "doc_ip",
    ["192.0.2.1", "192.0.2.255", "198.51.100.42", "203.0.113.7"],
)
def test_preserves_rfc_5737_documentation_ips(doc_ip: str) -> None:
    out = scrub(f"Connect to {doc_ip} as an example.")
    assert doc_ip in out
    assert IP_PLACEHOLDER not in out


@pytest.mark.unit
def test_idempotent() -> None:
    text = "alice@example.com is at 10.0.0.5"
    once = scrub(text)
    twice = scrub(once)
    assert once == twice


@pytest.mark.unit
def test_has_pii_detects_email() -> None:
    assert has_pii("user@host.org")
    assert not has_pii("hello world")


@pytest.mark.unit
def test_no_change_when_clean() -> None:
    text = "OAuth 2.0 defines four grant types."
    assert scrub(text) == text


@pytest.mark.unit
def test_handles_multiple_emails() -> None:
    out = scrub("a@x.com and b@y.com and c@z.org")
    assert out.count(EMAIL_PLACEHOLDER) == 3
