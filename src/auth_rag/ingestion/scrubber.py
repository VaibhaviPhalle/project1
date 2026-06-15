"""Lightweight PII scrubber for ingested text.

Scope is intentionally narrow at this stage:

  * Email addresses → ``[email-redacted]``.
  * IPv4 addresses that are not RFC 5737 documentation ranges → ``[ip-redacted]``.

Why a regex baseline (and not Presidio):
    For a public RFC corpus the realistic PII surface is author email
    addresses and the occasional example IP. A 30-line regex is enough for
    that, runs in microseconds, and adds no dependency. Presidio is the
    right answer if we ever ingest user-generated content (Step 9 stretch).

The scrubber is **deterministic** and **idempotent**. Calling it twice on
the same input yields the same output, byte-for-byte.
"""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
# Avoid scrubbing IPs in RFC 5737 documentation ranges (192.0.2.x, 198.51.100.x,
# 203.0.113.x), which appear constantly in RFC examples and aren't PII.
_IPV4_RE = re.compile(
    r"\b(?!(?:192\.0\.2|198\.51\.100|203\.0\.113)\.)"
    r"(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
)

EMAIL_PLACEHOLDER = "[email-redacted]"
IP_PLACEHOLDER = "[ip-redacted]"


def scrub(text: str) -> str:
    """Return a copy of ``text`` with emails and non-doc IPs redacted."""
    text = _EMAIL_RE.sub(EMAIL_PLACEHOLDER, text)
    return _IPV4_RE.sub(IP_PLACEHOLDER, text)


def has_pii(text: str) -> bool:
    """True if ``text`` contains content the scrubber would redact."""
    return bool(_EMAIL_RE.search(text) or _IPV4_RE.search(text))
