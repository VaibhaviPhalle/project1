"""Token counting backed by tiktoken.

Why tiktoken (and not transformers / sentencepiece):
    * It's the BPE used by GPT-3.5 / 4, which is the closest practical
      proxy for the prompt-budget arithmetic we'll do in Step 5/6.
    * Pure-Rust core; ~1 MB install footprint; no torch dependency.
    * Encoding files are vendored into the wheel (no first-run download
      required for ``cl100k_base``).

API:
    >>> tok = get_tokenizer("cl100k_base")
    >>> tok.count("hello world")
    2
    >>> tok.split_to_chunks("...", chunk_tokens=10, overlap_tokens=2)
    [...]

The tokenizer is loaded once per encoding name and cached for process
lifetime.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

import tiktoken

from auth_rag.exceptions import ConfigError

if TYPE_CHECKING:
    from collections.abc import Iterator


class Tokenizer:
    """Thin wrapper around a ``tiktoken.Encoding`` with the helpers we need."""

    __slots__ = ("_encoding", "encoding_name")

    def __init__(self, encoding_name: str) -> None:
        try:
            self._encoding = tiktoken.get_encoding(encoding_name)
        except (ValueError, KeyError) as exc:
            raise ConfigError(f"unknown tiktoken encoding: {encoding_name!r}") from exc
        self.encoding_name = encoding_name

    def count(self, text: str) -> int:
        """Number of tokens in ``text``."""
        if not text:
            return 0
        return len(self._encoding.encode(text, disallowed_special=()))

    def encode(self, text: str) -> list[int]:
        """Return token ids."""
        return self._encoding.encode(text, disallowed_special=())

    def decode(self, ids: list[int]) -> str:
        """Inverse of :meth:`encode`."""
        return self._encoding.decode(ids)

    def split_to_chunks(
        self,
        text: str,
        *,
        chunk_tokens: int,
        overlap_tokens: int,
    ) -> Iterator[tuple[str, int, int]]:
        """Yield ``(chunk_text, token_start, token_end)`` windows.

        Token offsets are within the encoded sequence — they're useful for
        debugging but most callers only care about the text and that
        chunks slide by ``chunk_tokens - overlap_tokens`` per step.

        Guarantees:
            * Each yielded chunk has at most ``chunk_tokens`` tokens.
            * Successive chunks share exactly ``overlap_tokens`` tokens
              of context (clamped at the boundary).
            * Empty input yields nothing.
        """
        if chunk_tokens <= 0:
            raise ValueError("chunk_tokens must be positive")
        if overlap_tokens < 0 or overlap_tokens >= chunk_tokens:
            raise ValueError("overlap_tokens must be in [0, chunk_tokens)")

        ids = self.encode(text)
        n = len(ids)
        if n == 0:
            return
        step = chunk_tokens - overlap_tokens
        start = 0
        while start < n:
            end = min(start + chunk_tokens, n)
            yield self.decode(ids[start:end]), start, end
            if end == n:
                break
            start += step


@lru_cache(maxsize=4)
def get_tokenizer(encoding_name: str = "cl100k_base") -> Tokenizer:
    """Return a process-cached :class:`Tokenizer` for ``encoding_name``."""
    return Tokenizer(encoding_name)
