"""Speech synthesis backed by Microsoft Edge's neural voices.

Why this engine: it is the only widely available neural TTS that needs no API
key, no credit card and no signup, and it still returns real word-boundary
timings. Those timings are what let the UI highlight words as they are spoken.

Everything here is measured, not guessed. Durations are read from the produced
audio, and word offsets are shifted by the actual length of the audio that came
before them, so a multi-chunk generation reports timings that line up with the
file you play.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field

import edge_tts
import mutagen.mp3

# edge-tts reports offsets in 100-nanosecond ticks, the same unit the Azure
# Speech SDK uses. 10,000 ticks make one millisecond.
_TICKS_PER_MS = 10_000


class SynthesisError(RuntimeError):
    """Raised when a chunk produces no audio."""


@dataclass(slots=True)
class WordTiming:
    start_ms: int
    end_ms: int
    text: str

    def as_dict(self) -> dict[str, int | str]:
        return {"start_ms": self.start_ms, "end_ms": self.end_ms, "text": self.text}


@dataclass(slots=True)
class ChunkAudio:
    index: int
    audio: bytes
    duration_ms: int
    words: list[WordTiming] = field(default_factory=list)


def mp3_duration_ms(data: bytes) -> int:
    """Duration of an MP3 held in memory, in milliseconds."""
    if not data:
        return 0
    handle = io.BytesIO(data)
    handle.name = "chunk.mp3"
    try:
        return int(round(mutagen.mp3.MP3(handle).info.length * 1000))
    except Exception as exc:  # noqa: BLE001 - mutagen raises several types
        raise SynthesisError(f"produced audio could not be read: {exc}") from exc


def _rate_arg(rate: float) -> str:
    """Convert a 0.5-2.0 multiplier into edge-tts's percentage string."""
    percent = int(round((rate - 1.0) * 100))
    return f"{percent:+d}%"


def _pitch_arg(pitch: float) -> str:
    """Convert semitones into the Hz offset edge-tts expects."""
    # One semitone is roughly 6% of a 200Hz reference, ~12Hz.
    hz = int(round(pitch * 12))
    return f"{hz:+d}Hz"


async def synthesize_chunk(
    text: str,
    *,
    voice: str,
    rate: float = 1.0,
    pitch: float = 0.0,
    volume: float = 1.0,
) -> tuple[bytes, list[WordTiming]]:
    """Synthesise one chunk and return its MP3 bytes plus word timings."""
    audio = bytearray()
    words: list[WordTiming] = []

    # edge-tts applies volume as a percentage offset, so 1.0 is +0%.
    volume_percent = int(round((volume - 1.0) * 100))
    communicate = edge_tts.Communicate(
        text,
        voice,
        rate=_rate_arg(rate),
        pitch=_pitch_arg(pitch),
        volume=f"{volume_percent:+d}%",
        boundary="WordBoundary",
    )

    try:
        async for event in communicate.stream():
            if event["type"] == "audio":
                audio.extend(event["data"])
            elif event["type"] == "WordBoundary":
                start = event["offset"] // _TICKS_PER_MS
                duration = event["duration"] // _TICKS_PER_MS
                words.append(
                    WordTiming(
                        start_ms=start,
                        end_ms=start + max(duration, 1),
                        text=event["text"],
                    )
                )
    except Exception as exc:  # noqa: BLE001 - network and protocol errors
        raise SynthesisError(f"speech service failed: {exc}") from exc

    if not audio:
        raise SynthesisError("speech service returned no audio for this chunk")

    return bytes(audio), words


async def synthesize(
    chunks: list[str],
    *,
    voice: str,
    rate: float = 1.0,
    pitch: float = 0.0,
    volume: float = 1.0,
    concurrency: int = 3,
) -> list[ChunkAudio]:
    """Synthesise every chunk, in order, with bounded concurrency.

    Chunks are independent, so a handful run in parallel. They are returned in
    the order given regardless of completion order.
    """
    if not chunks:
        return []

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def run(index: int, text: str) -> ChunkAudio:
        async with semaphore:
            audio, words = await synthesize_chunk(
                text, voice=voice, rate=rate, pitch=pitch, volume=volume
            )
            return ChunkAudio(
                index=index,
                audio=audio,
                duration_ms=mp3_duration_ms(audio),
                words=words,
            )

    return list(await asyncio.gather(*(run(i, c) for i, c in enumerate(chunks))))


def stitch(parts: list[ChunkAudio]) -> tuple[bytes, int, list[WordTiming]]:
    """Join chunk audio into one MP3 and rewrite word timings onto its timeline.

    Word boundaries from the service are relative to their own chunk. Each one
    is shifted by the real duration of everything before it, measured from the
    bytes rather than assumed, so the markers match the joined file.
    """
    ordered = sorted(parts, key=lambda p: p.index)
    buffer = bytearray()
    timeline: list[WordTiming] = []
    offset_ms = 0

    for part in ordered:
        for word in part.words:
            timeline.append(
                WordTiming(
                    start_ms=word.start_ms + offset_ms,
                    end_ms=word.end_ms + offset_ms,
                    text=word.text,
                )
            )
        buffer.extend(part.audio)
        offset_ms += part.duration_ms

    return bytes(buffer), offset_ms, timeline
