"""Recursive splitter for sections that exceed ``chunk_size_tokens``.

Algorithm (cribbed from LangChain's ``RecursiveCharacterTextSplitter`` but
re-implemented in <100 lines so we own the behavior and can test it):

  1. Try to split on paragraph boundaries (``\\n\\n``).
  2. If any resulting piece still exceeds the budget, recurse on it with
     sentence-ending punctuation as the next separator.
  3. Then word boundaries.
  4. Finally, hard-split on tokens (the tokenizer's own ``split_to_chunks``).

Token counting is delegated to :mod:`auth_rag.chunking.tokenizer`. This is
critical: word counts and character counts both correlate poorly with what
the LLM actually sees.

Returns ``list[str]`` (text only). The caller wraps these in
:class:`Chunk` objects with section metadata.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auth_rag.chunking.tokenizer import Tokenizer


# Ordered separator chain. Earlier entries preserve more semantic structure.
_SEPARATORS: tuple[str, ...] = (
    "\n\n",  # paragraph
    "\n",  # line
    ". ",  # sentence
    "; ",  # clause
    ", ",  # comma
    " ",  # word
    "",  # character (handled specially -- token-level fallback)
)


def split_text(
    text: str,
    *,
    tokenizer: Tokenizer,
    chunk_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """Split ``text`` into pieces each at most ``chunk_tokens`` tokens.

    Successive pieces overlap by ``overlap_tokens`` worth of trailing
    context. Empty input yields ``[]``.
    """
    if not text.strip():
        return []
    if tokenizer.count(text) <= chunk_tokens:
        return [text]

    pieces = list(
        _recursive_split(
            text, separators=_SEPARATORS, tokenizer=tokenizer, chunk_tokens=chunk_tokens
        )
    )
    return _merge_with_overlap(
        pieces,
        tokenizer=tokenizer,
        chunk_tokens=chunk_tokens,
        overlap_tokens=overlap_tokens,
    )


def _recursive_split(
    text: str,
    *,
    separators: tuple[str, ...],
    tokenizer: Tokenizer,
    chunk_tokens: int,
) -> Iterable[str]:
    """Yield atomic pieces (each <= chunk_tokens) without merging."""
    if tokenizer.count(text) <= chunk_tokens:
        if text.strip():
            yield text
        return

    if not separators:
        # Token-level fallback -- guaranteed to terminate.
        for chunk_text, _, _ in tokenizer.split_to_chunks(
            text, chunk_tokens=chunk_tokens, overlap_tokens=0
        ):
            yield chunk_text
        return

    sep, *rest = separators
    if sep == "":
        # Same as the empty-separators case above.
        for chunk_text, _, _ in tokenizer.split_to_chunks(
            text, chunk_tokens=chunk_tokens, overlap_tokens=0
        ):
            yield chunk_text
        return

    parts = _split_keep_separator(text, sep)
    for part in parts:
        yield from _recursive_split(
            part,
            separators=tuple(rest),
            tokenizer=tokenizer,
            chunk_tokens=chunk_tokens,
        )


def _split_keep_separator(text: str, sep: str) -> list[str]:
    """Like ``str.split`` but keeps ``sep`` attached to the preceding chunk
    so concatenation reproduces the original text."""
    if sep == "":
        return [text]
    pattern = re.escape(sep)
    pieces = re.split(f"({pattern})", text)
    out: list[str] = []
    for i in range(0, len(pieces), 2):
        body = pieces[i]
        delimiter = pieces[i + 1] if i + 1 < len(pieces) else ""
        if body or delimiter:
            out.append(body + delimiter)
    return out


def _merge_with_overlap(
    pieces: list[str],
    *,
    tokenizer: Tokenizer,
    chunk_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """Greedy-pack pieces into chunks of <= chunk_tokens with overlap.

    Overlap is implemented by carrying the trailing ``overlap_tokens``
    worth of pieces from the previous chunk into the next one.
    """
    if not pieces:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for piece in pieces:
        piece_tokens = tokenizer.count(piece)
        if current_tokens + piece_tokens <= chunk_tokens:
            current.append(piece)
            current_tokens += piece_tokens
            continue

        if current:
            chunks.append("".join(current))
            current = _tail_for_overlap(current, tokenizer=tokenizer, overlap_tokens=overlap_tokens)
            current_tokens = sum(tokenizer.count(p) for p in current)

        if piece_tokens > chunk_tokens:
            # Single piece bigger than budget -- split it on tokens directly
            # and emit each split as its own chunk (no merging across them).
            for sub_text, _, _ in tokenizer.split_to_chunks(
                piece,
                chunk_tokens=chunk_tokens,
                overlap_tokens=overlap_tokens,
            ):
                chunks.append(sub_text)
            current = []
            current_tokens = 0
            continue

        current.append(piece)
        current_tokens += piece_tokens

    if current:
        chunks.append("".join(current))
    return chunks


def _tail_for_overlap(pieces: list[str], *, tokenizer: Tokenizer, overlap_tokens: int) -> list[str]:
    """Return the suffix of ``pieces`` whose total token count <= overlap_tokens."""
    if overlap_tokens <= 0:
        return []
    tail: list[str] = []
    total = 0
    for piece in reversed(pieces):
        cost = tokenizer.count(piece)
        if total + cost > overlap_tokens:
            break
        tail.insert(0, piece)
        total += cost
    return tail
