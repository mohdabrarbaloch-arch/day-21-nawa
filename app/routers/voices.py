"""The voice catalog and the text preview endpoint."""

from fastapi import APIRouter, Request

from app import voices as catalog
from app.limiter import limiter
from app.schemas import PreviewIn, PreviewOut
from app.services import chunker
from app.services.normaliser import normalise

router = APIRouter()


def all_voices() -> list[dict[str, str]]:
    return [v.as_dict() for v in catalog.VOICES]


@router.get("/voices")
def list_voices() -> dict[str, object]:
    """Curated voices, grouped by language for the picker."""
    return {
        "default": catalog.DEFAULT_VOICE,
        "total": len(catalog.VOICES),
        "languages": catalog.languages(),
    }


@router.post("/preview")
@limiter.limit("40/minute")
def preview_text(request: Request, payload: PreviewIn) -> PreviewOut:
    """Show what the text will become, without spending a synthesis call.

    This is the endpoint that makes the value visible: type a rupee amount and
    watch it turn into the words a person would say.
    """
    after = normalise(payload.text, apply=payload.normalise)
    chunks = chunker.split(after)
    return PreviewOut(
        before=payload.text,
        after=after,
        chunks=chunks,
        estimated_seconds=chunker.estimate_seconds(chunks),
        char_count=len(after),
    )
