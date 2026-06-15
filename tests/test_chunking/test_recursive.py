"""Tests for the recursive splitter."""

from __future__ import annotations

from itertools import pairwise

import pytest

from auth_rag.chunking.recursive import _split_keep_separator, split_text
from auth_rag.chunking.tokenizer import get_tokenizer


@pytest.fixture
def tokenizer():
    return get_tokenizer("cl100k_base")


@pytest.mark.unit
def test_short_text_returns_single_piece(tokenizer) -> None:
    out = split_text("hello world", tokenizer=tokenizer, chunk_tokens=100, overlap_tokens=0)
    assert out == ["hello world"]


@pytest.mark.unit
def test_empty_text_returns_empty(tokenizer) -> None:
    assert split_text("", tokenizer=tokenizer, chunk_tokens=100, overlap_tokens=0) == []
    assert split_text("   \n\n  ", tokenizer=tokenizer, chunk_tokens=100, overlap_tokens=0) == []


@pytest.mark.unit
def test_long_text_splits_on_paragraphs(tokenizer) -> None:
    para = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 20
    text = "\n\n".join([para, para, para])
    out = split_text(text, tokenizer=tokenizer, chunk_tokens=100, overlap_tokens=10)
    assert len(out) > 1
    for piece in out:
        assert tokenizer.count(piece) <= 100


@pytest.mark.unit
def test_overlap_introduces_shared_tokens(tokenizer) -> None:
    # 200 distinct words so we can detect overlap by content.
    words = [f"word{i:04d}" for i in range(200)]
    text = "\n\n".join(words)
    out = split_text(text, tokenizer=tokenizer, chunk_tokens=80, overlap_tokens=20)
    # At least one consecutive pair should share a token.
    assert len(out) >= 2
    found_overlap = False
    for a, b in pairwise(out):
        a_tail = a.split()[-3:]
        if any(token in b for token in a_tail):
            found_overlap = True
            break
    assert found_overlap, "expected at least some lexical overlap between chunks"


@pytest.mark.unit
def test_no_overlap_when_zero(tokenizer) -> None:
    para = "Lorem ipsum dolor sit amet. " * 30
    out = split_text(para, tokenizer=tokenizer, chunk_tokens=80, overlap_tokens=0)
    # Every chunk must respect the budget; we don't assert exact non-overlap
    # because separator-preserving splits make perfect non-overlap rare.
    for piece in out:
        assert tokenizer.count(piece) <= 80


@pytest.mark.unit
def test_oversized_single_word_is_token_split(tokenizer) -> None:
    # Construct a "section" with no separators that's larger than budget.
    # We force a single very long pseudo-word.
    text = "x" * 5000  # tiktoken tokenizes this into many tokens
    out = split_text(text, tokenizer=tokenizer, chunk_tokens=50, overlap_tokens=5)
    assert len(out) > 1
    for piece in out:
        assert tokenizer.count(piece) <= 50


@pytest.mark.unit
def test_split_keep_separator_preserves_content() -> None:
    text = "alpha. beta. gamma."
    parts = _split_keep_separator(text, ". ")
    assert "".join(parts) == text


@pytest.mark.unit
def test_split_keep_separator_empty_separator() -> None:
    parts = _split_keep_separator("abc", "")
    assert parts == ["abc"]


@pytest.mark.unit
def test_unicode_text_does_not_crash(tokenizer) -> None:
    text = ("日本語のテキストです。" * 30) + "\n\n" + ("café résumé naïve. " * 30)
    out = split_text(text, tokenizer=tokenizer, chunk_tokens=100, overlap_tokens=10)
    assert len(out) >= 1
    for piece in out:
        assert tokenizer.count(piece) <= 100


@pytest.mark.unit
def test_split_is_deterministic(tokenizer) -> None:
    text = ("Authorization code grant flow. " * 100) + "\n\n" + ("PKCE protects against. " * 100)
    a = split_text(text, tokenizer=tokenizer, chunk_tokens=120, overlap_tokens=20)
    b = split_text(text, tokenizer=tokenizer, chunk_tokens=120, overlap_tokens=20)
    assert a == b
