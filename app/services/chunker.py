"""Split text into pieces a synthesiser can say in one breath.

A synthesiser given a 900 word blob will either truncate or rush. Given a
sentence it produces something you would actually listen to.

The chunker therefore prefers sentence ends, falls back to clause breaks, and
only splits mid-clause when a single sentence is longer than the limit. It also
guards against producing a fragment too short to carry prosody — a two word
tail like "Yes." gets merged into its neighbour instead of being sent alone.
"""

from __future__ import annotations

import re

DEFAULT_MAX_CHARS = 280
DEFAULT_MIN_CHARS = 40

# Two or more newlines is a paragraph break, which earns a longer pause.
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")

# Sentence ends. The lookbehind stops us cutting "Dr." or "3.5" in half.
_SENTENCE_END = re.compile(r"(?<=[.!?])[\"'\u201d\u2019)]*\s+")

# Clause ends, used only when a sentence is too long for one chunk.
_CLAUSE_BREAK = re.compile(r"(?<=[,;:\u2014-])\s+")


def _split_keeping(text: str, pattern: re.Pattern[str]) -> list[str]:
    """Split on a pattern without losing the delimiter."""
    pieces: list[str] = []
    last = 0
    for match in pattern.finditer(text):
        end = match.end()
        pieces.append(text[last:end])
        last = end
    if last < len(text):
        pieces.append(text[last:])
    return [p for p in (p.strip() for p in pieces) if p]


def _hard_split(sentence: str, max_chars: int) -> list[str]:
    """Last resort: break on a word boundary inside an over-long sentence.

    A single "word" longer than the limit (a URL, a long identifier) is cut
    mid-word rather than allowed through, so every piece fits.
    """
    words = sentence.split()
    parts: list[str] = []
    current: list[str] = []
    for word in words:
        if len(word) > max_chars:
            if current:
                parts.append(" ".join(current))
                current = []
            parts.extend(word[i : i + max_chars] for i in range(0, len(word), max_chars))
            continue
        candidate = " ".join([*current, word])
        if current and len(candidate) > max_chars:
            parts.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        parts.append(" ".join(current))
    return parts


def _pack(pieces: list[str], max_chars: int) -> list[str]:
    """Greedily join small pieces so each chunk is worth speaking."""
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current} {piece}".strip() if current else piece
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks


def _merge_short_tail(chunks: list[str], min_chars: int, max_chars: int) -> list[str]:
    """Fold a too-short final chunk into the one before it.

    The merge is only allowed when the result still fits the limit. Without
    that check a 79 character chunk plus a 39 character tail becomes a 119
    character chunk, which is exactly what the limit exists to prevent.
    """
    if len(chunks) < 2 or len(chunks[-1]) >= min_chars:
        return chunks
    merged = f"{chunks[-2]} {chunks[-1]}"
    if len(merged) <= max_chars:
        return [*chunks[:-2], merged]
    return chunks


def split(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> list[str]:
    """Return the text as an ordered list of speakable chunks."""
    if not text or not text.strip():
        return []

    if max_chars < 40:
        raise ValueError("max_chars must be at least 40 to keep speech natural")

    chunks: list[str] = []
    for paragraph in _PARAGRAPH_BREAK.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        # Each paragraph is packed on its own. Packing across the whole text
        # would merge two short paragraphs into one chunk and lose the pause
        # between them.
        paragraph_chunks: list[str] = []

        sentences = _split_keeping(paragraph, _SENTENCE_END)

        expanded: list[str] = []
        for sentence in sentences:
            if len(sentence) <= max_chars:
                expanded.append(sentence)
                continue
            # Too long: try clause boundaries, then settle for a word split.
            clauses = _split_keeping(sentence, _CLAUSE_BREAK)
            if all(len(c) <= max_chars for c in clauses) and len(clauses) > 1:
                expanded.extend(clauses)
            else:
                expanded.extend(_hard_split(sentence, max_chars))

        paragraph_chunks.extend(_pack(expanded, max_chars))
        chunks.extend(_merge_short_tail(paragraph_chunks, min_chars, max_chars))

    return [c.strip() for c in chunks if c.strip()]


def estimate_seconds(chunks: list[str], *, chars_per_second: float = 14.5) -> float:
    """Rough spoken length, used only for the pre-flight estimate in the UI.

    The real duration comes from the audio itself; this exists so the form can
    tell you "about 40 seconds" before you spend a round trip.
    """
    total = sum(len(c) for c in chunks)
    return round(total / chars_per_second, 1) if total else 0.0
