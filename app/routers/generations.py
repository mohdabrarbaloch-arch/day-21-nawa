"""Generation lifecycle: create, poll, listen, edit one paragraph.

Synthesis is slow enough that doing it inside the request would be a bad
experience and a bad idea. POST returns 202 with a queued job; the client polls
until it is completed. Every job is resumable at chunk granularity, so a single
bad paragraph can be re-recorded without paying for the whole script again.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import voices as catalog
from app.config import settings
from app.database import SessionLocal
from app.deps import CurrentUser, DbSession
from app.limiter import limiter
from app.models import Chunk, Generation, GenerationStatus, Pronunciation
from app.schemas import (
    ChunkOut,
    GenerationCreate,
    GenerationDetail,
    GenerationListOut,
    GenerationOut,
    UsageOut,
    WordOut,
)
from app.security import create_audio_token, decode_audio_token
from app.services import chunker, synth
from app.services.normaliser import apply_lexicon, normalise

logger = logging.getLogger("nawa.generations")
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _audio_url(generation_id: int, user_id: int) -> str:
    token = create_audio_token(user_id, generation_id)
    return f"/api/generations/{generation_id}/audio?t={token}"


def _to_out(generation: Generation, user_id: int) -> GenerationOut:
    payload = GenerationOut(
        id=generation.id,
        title=generation.title,
        voice=generation.voice,
        voice_label=generation.voice_label,
        rate=generation.rate,
        pitch=generation.pitch,
        volume=generation.volume,
        status=generation.status,
        error=generation.error,
        duration_ms=generation.duration_ms,
        char_count=generation.char_count,
        chunk_count=generation.chunk_count,
        created_at=generation.created_at,
        completed_at=generation.completed_at,
    )
    if generation.status == GenerationStatus.COMPLETED:
        payload.audio_url = _audio_url(generation.id, user_id)
    return payload


def _timeline(chunks: list[Chunk]) -> list[dict[str, int | str]]:
    """Shift per-chunk word timings onto the stitched timeline."""
    timeline: list[dict[str, int | str]] = []
    offset = 0
    for chunk in sorted(chunks, key=lambda c: c.index):
        for word in chunk.words or []:
            timeline.append(
                {
                    "start_ms": int(word["start_ms"]) + offset,
                    "end_ms": int(word["end_ms"]) + offset,
                    "text": str(word["text"]),
                }
            )
        offset += chunk.duration_ms
    return timeline


def _owned(db: Session, generation_id: int, user_id: int) -> Generation:
    generation = db.get(Generation, generation_id)
    # Deliberately 404, not 403. A request should not learn that a record it
    # cannot read exists.
    if generation is None or generation.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
    return generation


def _lexicon(db: Session, user_id: int) -> dict[str, str]:
    rows = db.scalars(
        select(Pronunciation).where(
            Pronunciation.user_id == user_id, Pronunciation.enabled.is_(True)
        )
    ).all()
    return {row.written: row.spoken for row in rows}


# ---------------------------------------------------------------------------
# Background synthesis
# ---------------------------------------------------------------------------


def _prepare_text(db: Session, text: str, user_id: int, do_normalise: bool) -> str:
    return apply_lexicon(normalise(text, apply=do_normalise), _lexicon(db, user_id))


def _run_synthesis(generation_id: int) -> None:
    """Synthesise every chunk of a generation. Runs after the response.

    Opens its own session: the request's session is closed by the time this
    executes.
    """
    db = SessionLocal()
    try:
        generation = db.get(Generation, generation_id)
        if generation is None:
            return

        generation.status = GenerationStatus.PROCESSING
        db.commit()

        texts = chunker.split(generation.normalised_text)
        parts = asyncio.run(
            synth.synthesize(
                texts,
                voice=generation.voice,
                rate=generation.rate,
                pitch=generation.pitch,
                volume=generation.volume,
                concurrency=settings.synth_concurrency,
            )
        )

        db.execute(delete(Chunk).where(Chunk.generation_id == generation.id))
        for part in sorted(parts, key=lambda p: p.index):
            db.add(
                Chunk(
                    generation_id=generation.id,
                    index=part.index,
                    text=texts[part.index],
                    duration_ms=part.duration_ms,
                    audio=part.audio,
                    words=[w.as_dict() for w in part.words],
                )
            )

        total_ms = sum(p.duration_ms for p in parts)
        generation.duration_ms = total_ms
        generation.chunk_count = len(parts)
        generation.status = GenerationStatus.COMPLETED
        generation.completed_at = datetime.now(UTC)
        generation.error = ""
        db.commit()
        logger.info(
            "generation %s completed: %d chunks, %d ms",
            generation_id,
            len(parts),
            total_ms,
        )
    except Exception as exc:  # noqa: BLE001 - any failure ends the job
        logger.exception("generation %s failed", generation_id)
        db.rollback()
        generation = db.get(Generation, generation_id)
        if generation is not None:
            generation.status = GenerationStatus.FAILED
            generation.error = str(exc)[:500]
            db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/usage", response_model=UsageOut)
def usage(user: CurrentUser, db: DbSession) -> UsageOut:
    since = datetime.now(UTC) - timedelta(days=1)
    used = db.scalar(
        select(func.count(Generation.id)).where(
            Generation.user_id == user.id, Generation.created_at >= since
        )
    )
    used = int(used or 0)
    return UsageOut(
        used_today=used,
        limit=settings.max_generations_per_day,
        remaining=max(0, settings.max_generations_per_day - used),
    )


@router.post("", response_model=GenerationOut, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/minute")
def create_generation(
    request: Request,
    payload: GenerationCreate,
    user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
) -> GenerationOut:
    since = datetime.now(UTC) - timedelta(days=1)
    used = db.scalar(
        select(func.count(Generation.id)).where(
            Generation.user_id == user.id, Generation.created_at >= since
        )
    )
    if int(used or 0) >= settings.max_generations_per_day:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily limit of {settings.max_generations_per_day} generations reached. "
                "It resets 24 hours after your oldest one today."
            ),
        )

    prepared = _prepare_text(db, payload.text, user.id, payload.normalise)
    chunks = chunker.split(prepared)
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That text has nothing to speak",
        )
    if len(chunks) > settings.max_chunks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"That is {len(chunks)} chunks; the limit is {settings.max_chunks}. "
                "Shorten the text and split it into two generations."
            ),
        )

    voice = catalog.get_voice(payload.voice)
    generation = Generation(
        user_id=user.id,
        title=payload.title.strip() or payload.text.strip()[:60],
        text=payload.text,
        normalised_text=prepared,
        voice=payload.voice,
        voice_label=f"{voice.label} — {voice.language}" if voice else payload.voice,
        rate=payload.rate,
        pitch=payload.pitch,
        volume=payload.volume,
        status=GenerationStatus.QUEUED,
        char_count=len(prepared),
        chunk_count=len(chunks),
    )
    db.add(generation)
    db.commit()
    db.refresh(generation)

    background.add_task(_run_synthesis, generation.id)

    return _to_out(generation, user.id)


@router.get("", response_model=GenerationListOut)
def list_generations(
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GenerationListOut:
    total = db.scalar(select(func.count(Generation.id)).where(Generation.user_id == user.id))
    rows = db.scalars(
        select(Generation)
        .where(Generation.user_id == user.id)
        .order_by(Generation.created_at.desc(), Generation.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return GenerationListOut(
        items=[_to_out(g, user.id) for g in rows],
        total=int(total or 0),
    )


@router.get("/{generation_id}", response_model=GenerationDetail)
def get_generation(generation_id: int, user: CurrentUser, db: DbSession) -> GenerationDetail:
    generation = _owned(db, generation_id, user.id)
    chunks = db.scalars(
        select(Chunk).where(Chunk.generation_id == generation.id).order_by(Chunk.index)
    ).all()

    base = _to_out(generation, user.id)
    return GenerationDetail(
        **base.model_dump(),
        text=generation.text,
        normalised_text=generation.normalised_text,
        chunks=[ChunkOut(index=c.index, text=c.text, duration_ms=c.duration_ms) for c in chunks],
        words=[WordOut(**w) for w in _timeline(list(chunks))],
    )


@router.get("/{generation_id}/audio")
def get_audio(
    generation_id: int,
    db: DbSession,
    t: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Query()] = None,
) -> Response:
    """Stream the stitched MP3.

    Accepts a short-lived capability token in the query string so the URL can
    go straight into an <audio> element. A session token works too, for API
    clients that prefer headers.
    """
    generation = db.get(Generation, generation_id)
    if generation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")

    user_id = decode_audio_token(t, generation_id) if t else None
    if user_id is None:
        from app.security import decode_access_token

        header_token = None
        if authorization and authorization.lower().startswith("bearer "):
            header_token = authorization.split(" ", 1)[1].strip()
        user_id = decode_access_token(header_token) if header_token else None
    if user_id is None or user_id != generation.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid audio token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if generation.status != GenerationStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Audio is not ready (status: {generation.status})",
        )

    chunks = db.scalars(
        select(Chunk).where(Chunk.generation_id == generation.id).order_by(Chunk.index)
    ).all()
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="No audio stored for this generation"
        )

    body = b"".join(c.audio for c in chunks)
    filename = f"nawa-{generation.id}.mp3"
    return Response(
        content=body,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Content-Length": str(len(body)),
            "Cache-Control": "private, max-age=3600",
            "Accept-Ranges": "none",
        },
    )


@router.post("/{generation_id}/retry", response_model=GenerationOut)
@limiter.limit("20/minute")
def retry_generation(
    request: Request,
    generation_id: int,
    user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
) -> GenerationOut:
    generation = _owned(db, generation_id, user.id)
    if generation.status not in {GenerationStatus.FAILED, GenerationStatus.QUEUED}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a failed or queued generation can be retried",
        )

    generation.status = GenerationStatus.QUEUED
    generation.error = ""
    db.commit()
    background.add_task(_run_synthesis, generation.id)
    return _to_out(generation, user.id)


@router.post("/{generation_id}/chunks/{index}/resynthesize", response_model=GenerationDetail)
@limiter.limit("20/minute")
def resynthesize_chunk(
    request: Request,
    generation_id: int,
    index: int,
    user: CurrentUser,
    db: DbSession,
) -> GenerationDetail:
    """Re-record one chunk, keeping the rest of the audio untouched."""
    generation = _owned(db, generation_id, user.id)
    if generation.status != GenerationStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This generation has not finished yet",
        )

    chunk = db.scalar(
        select(Chunk).where(Chunk.generation_id == generation.id, Chunk.index == index)
    )
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")

    try:
        audio, words = asyncio.run(
            synth.synthesize_chunk(
                chunk.text,
                voice=generation.voice,
                rate=generation.rate,
                pitch=generation.pitch,
                volume=generation.volume,
            )
        )
    except synth.SynthesisError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    chunk.audio = audio
    chunk.duration_ms = synth.mp3_duration_ms(audio)
    chunk.words = [w.as_dict() for w in words]

    total = db.scalar(
        select(func.coalesce(func.sum(Chunk.duration_ms), 0)).where(
            Chunk.generation_id == generation.id
        )
    )
    generation.duration_ms = int(total or 0)
    db.commit()

    return get_generation(generation_id, user, db)


@router.patch("/{generation_id}", response_model=GenerationOut)
def rename_generation(
    generation_id: int,
    user: CurrentUser,
    db: DbSession,
    title: Annotated[str, Query(min_length=1, max_length=140)],
) -> GenerationOut:
    generation = _owned(db, generation_id, user.id)
    generation.title = title.strip() or generation.title
    db.commit()
    db.refresh(generation)
    return _to_out(generation, user.id)


@router.get("/{generation_id}/download")
def download_audio(
    generation_id: int,
    db: DbSession,
    t: Annotated[str | None, Query()] = None,
) -> StreamingResponse:
    """Same bytes as /audio, served as a download."""
    response = get_audio(generation_id, db, t=t)
    return StreamingResponse(
        iter([response.body]),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f'attachment; filename="nawa-{generation_id}.mp3"',
            "Content-Length": str(len(response.body)),
        },
    )


@router.delete("/{generation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_generation(generation_id: int, user: CurrentUser, db: DbSession) -> Response:
    generation = _owned(db, generation_id, user.id)
    db.delete(generation)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
