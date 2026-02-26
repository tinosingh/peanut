"""Character-aware text chunker.

nomic-embed-text uses a BERT WordPiece tokenizer with a 2048-token context
window.  BERT token counts vary wildly by language — Swedish/Finnish text
averages ~1.2 chars per token versus ~4 chars per token for English.

Because tiktoken (cl100k_base / GPT) has *no* correlation with BERT token
counts, this module enforces a conservative **character limit** derived from
the worst-case language in the corpus:

    2048 BERT tokens × 1.2 chars/token ≈ 2,400 chars (hard ceiling)

Chunk size and overlap are still expressed in characters (not tokens) and
read from the config table at ingest time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Hard ceiling: nomic-embed-text context_length = 2048 BERT tokens.
# Swedish/Finnish ≈ 1.2 chars/token → 2048 × 1.2 ≈ 2,457 chars.
# Use 2000 for a safe margin.
MAX_CHUNK_CHARS = 2000


@dataclass
class Chunk:
    index: int
    text: str
    char_count: int


def chunk_text(
    text: str,
    chunk_size: int = 1800,
    overlap: int = 200,
) -> list[Chunk]:
    """Split *text* into overlapping chunks that fit within the embedding
    model's context window.

    All sizes are in **characters** (not tokens) because the relevant
    tokenizer is BERT WordPiece, and the chars-per-token ratio is
    language-dependent.  The hard ceiling ``MAX_CHUNK_CHARS`` guarantees
    every chunk is safe for nomic-embed-text regardless of language.

    Args:
        text:       Input text.
        chunk_size: Target characters per chunk (default 1800).
        overlap:    Character overlap between consecutive chunks (default 200).

    Returns:
        List of :class:`Chunk` objects ordered by index.
    """
    if not text or not text.strip():
        return []

    # Effective target must never exceed the hard ceiling.
    target = min(chunk_size, MAX_CHUNK_CHARS)

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[Chunk] = []
    current: list[str] = []
    current_chars = 0
    chunk_idx = 0

    for sentence in sentences:
        s_len = len(sentence)

        # If a single sentence exceeds the hard ceiling, hard-split it.
        if s_len > MAX_CHUNK_CHARS:
            # Flush anything accumulated so far.
            if current:
                chunk_str = " ".join(current)
                chunks.append(Chunk(chunk_idx, chunk_str, len(chunk_str)))
                chunk_idx += 1
                current, current_chars = [], 0

            # Split long sentence on word boundaries.
            words = sentence.split()
            buf: list[str] = []
            buf_chars = 0
            for word in words:
                # +1 for the space that joins words
                added = len(word) + (1 if buf else 0)
                if buf_chars + added > MAX_CHUNK_CHARS and buf:
                    chunk_str = " ".join(buf)
                    chunks.append(Chunk(chunk_idx, chunk_str, len(chunk_str)))
                    chunk_idx += 1
                    buf, buf_chars = [], 0
                buf.append(word)
                buf_chars += added
            if buf:
                # Remainder goes into ``current`` for normal flow.
                current = buf
                current_chars = buf_chars
            continue

        # Normal path: accumulate sentences up to *target*.
        if current_chars + len(sentence) + 1 > target and current:
            chunk_str = " ".join(current)
            chunks.append(Chunk(chunk_idx, chunk_str, len(chunk_str)))
            chunk_idx += 1

            # Seed next chunk with overlap characters from the tail.
            overlap_words: list[str] = []
            overlap_chars = 0
            for word in reversed(chunk_str.split()):
                added = len(word) + (1 if overlap_words else 0)
                if overlap_chars + added > overlap:
                    break
                overlap_words.insert(0, word)
                overlap_chars += added
            current = overlap_words
            current_chars = overlap_chars

        current.append(sentence)
        current_chars += s_len + (1 if len(current) > 1 else 0)

    # Flush remaining.
    if current:
        chunk_str = " ".join(current)
        chunks.append(Chunk(chunk_idx, chunk_str, len(chunk_str)))

    return chunks
