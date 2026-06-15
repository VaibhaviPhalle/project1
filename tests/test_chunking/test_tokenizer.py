"""Tests for the tiktoken-backed tokenizer wrapper."""

from __future__ import annotations

import pytest

from auth_rag.chunking.tokenizer import Tokenizer, get_tokenizer
from auth_rag.exceptions import ConfigError


@pytest.mark.unit
def test_get_tokenizer_returns_singleton() -> None:
    a = get_tokenizer("cl100k_base")
    b = get_tokenizer("cl100k_base")
    assert a is b


@pytest.mark.unit
def test_unknown_encoding_raises() -> None:
    with pytest.raises(ConfigError, match="unknown tiktoken encoding"):
        Tokenizer("not-a-real-encoding")


@pytest.mark.unit
def test_count_empty_string_is_zero() -> None:
    tok = get_tokenizer("cl100k_base")
    assert tok.count("") == 0


@pytest.mark.unit
def test_count_simple_text() -> None:
    tok = get_tokenizer("cl100k_base")
    n = tok.count("The OAuth 2.0 framework defines four grant types.")
    assert 8 <= n <= 14  # tiktoken-specific exact value not the point of this test


@pytest.mark.unit
def test_encode_decode_round_trip() -> None:
    tok = get_tokenizer("cl100k_base")
    text = "RFC 6749 §4.1 — Authorization Code Grant"
    assert tok.decode(tok.encode(text)) == text


@pytest.mark.unit
def test_split_to_chunks_yields_overlapping_windows() -> None:
    tok = get_tokenizer("cl100k_base")
    text = " ".join([f"word{i}" for i in range(200)])
    chunks = list(tok.split_to_chunks(text, chunk_tokens=50, overlap_tokens=10))
    assert len(chunks) >= 2
    for chunk_text, start, end in chunks:
        assert end - start <= 50
        assert chunk_text.strip()


@pytest.mark.unit
def test_split_to_chunks_overlap_step_correct() -> None:
    tok = get_tokenizer("cl100k_base")
    text = " ".join([f"word{i}" for i in range(200)])
    windows = list(tok.split_to_chunks(text, chunk_tokens=50, overlap_tokens=10))
    # Successive windows should advance by chunk_tokens - overlap_tokens = 40,
    # except the last one which may stop short.
    for i in range(len(windows) - 1):
        _, start_a, end_a = windows[i]
        _, start_b, _ = windows[i + 1]
        assert end_a - start_a == 50 or i == len(windows) - 1
        assert start_b - start_a == 40


@pytest.mark.unit
def test_split_to_chunks_empty_input() -> None:
    tok = get_tokenizer("cl100k_base")
    assert list(tok.split_to_chunks("", chunk_tokens=10, overlap_tokens=2)) == []


@pytest.mark.unit
def test_split_to_chunks_rejects_bad_params() -> None:
    tok = get_tokenizer("cl100k_base")
    with pytest.raises(ValueError, match="chunk_tokens"):
        list(tok.split_to_chunks("hi", chunk_tokens=0, overlap_tokens=0))
    with pytest.raises(ValueError, match="overlap_tokens"):
        list(tok.split_to_chunks("hi", chunk_tokens=10, overlap_tokens=10))
    with pytest.raises(ValueError, match="overlap_tokens"):
        list(tok.split_to_chunks("hi", chunk_tokens=10, overlap_tokens=-1))


@pytest.mark.unit
def test_unicode_token_counts_consistent() -> None:
    tok = get_tokenizer("cl100k_base")
    # Multi-byte unicode shouldn't crash and should count > 0.
    assert tok.count("résumé café naïve") > 0
    assert tok.count("日本語のテキスト") > 0
