"""Per-user pronunciation overrides.

The accent problem: a synthesiser reading "Nawa" or "Baloch" gets it wrong
every time. Rather than hoping the engine learns, let the person write the
spoken form once and apply it to everything they generate after that.
"""

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import CurrentUser, DbSession
from app.models import Pronunciation
from app.schemas import PronunciationIn, PronunciationOut

router = APIRouter()

MAX_ENTRIES = 200


@router.get("", response_model=list[PronunciationOut])
def list_entries(user: CurrentUser, db: DbSession) -> list[PronunciationOut]:
    rows = db.scalars(
        select(Pronunciation)
        .where(Pronunciation.user_id == user.id)
        .order_by(Pronunciation.written)
    ).all()
    return [PronunciationOut.model_validate(r) for r in rows]


@router.post("", response_model=PronunciationOut, status_code=status.HTTP_201_CREATED)
def create_entry(payload: PronunciationIn, user: CurrentUser, db: DbSession) -> PronunciationOut:
    count = len(db.scalars(select(Pronunciation.id).where(Pronunciation.user_id == user.id)).all())
    if count >= MAX_ENTRIES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You have reached the limit of {MAX_ENTRIES} entries",
        )

    entry = Pronunciation(user_id=user.id, written=payload.written, spoken=payload.spoken)
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an entry for that word",
        ) from None
    db.refresh(entry)
    return PronunciationOut.model_validate(entry)


@router.patch("/{entry_id}", response_model=PronunciationOut)
def update_entry(
    entry_id: int,
    payload: PronunciationIn,
    user: CurrentUser,
    db: DbSession,
) -> PronunciationOut:
    entry = db.scalar(
        select(Pronunciation).where(Pronunciation.id == entry_id, Pronunciation.user_id == user.id)
    )
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

    entry.written = payload.written
    entry.spoken = payload.spoken
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an entry for that word",
        ) from None
    db.refresh(entry)
    return PronunciationOut.model_validate(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: int, user: CurrentUser, db: DbSession) -> Response:
    entry = db.scalar(
        select(Pronunciation).where(Pronunciation.id == entry_id, Pronunciation.user_id == user.id)
    )
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    db.delete(entry)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
