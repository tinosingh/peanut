"""Token-aware text chunker.

Approximates token count using word count (1 word ≈ 1.3 tokens).
Chunk size and overlap are read from the config table at ingest time.

For production, swap the tokenizer with tiktoken or a sentence-transformers
tokenizer for exact counts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    index: int
    text: str
    token_estimate: int


def _word_count(text: str) -> int:
    return len(text.split())


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: 1.3 tokens per word."""
    return int(_word_count(text) * 1.3)


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 50,
) -> list[Chunk]:
    """Split text into overlapping token-approximate chunks.

    Args:
        text:       Input text.
        chunk_size: Target tokens per chunk (default from config table).
        overlap:    Token overlap between consecutive chunks.

    Returns:
        List of Chunk objects with index, text, and token estimate.
    """
    if not text.strip():
        return []

    # Split into sentences for cleaner boundaries
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[Chunk] = []
    current: list[str] = []
    current_tokens = 0
    chunk_idx = 0

    # Overlap buffer (last N words)
    overlap_words_target = int(overlap / 1.3)

    for sentence in sentences:
        s_tokens = _estimate_tokens(sentence)

        if current_tokens + s_tokens > chunk_size and current:
            chunk_text_str = " ".join(current)
            chunks.append(Chunk(
                index=chunk_idx,
                text=chunk_text_str,
                token_estimate=current_tokens,
            ))
            chunk_idx += 1

            # Seed next chunk with overlap (last N words of current chunk)
            all_words = chunk_text_str.split()
            overlap_words = all_words[-overlap_words_target:] if overlap_words_target > 0 else []
            current = overlap_words
            current_tokens = _estimate_tokens(" ".join(current))

        current.append(sentence)
        current_tokens += s_tokens

    # Flush remaining
    if current:
        chunks.append(Chunk(
            index=chunk_idx,
            text=" ".join(current),
            token_estimate=current_tokens,
        ))

    return chunks
