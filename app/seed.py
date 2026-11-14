"""Create the demo account and a couple of finished generations.

Run with:  python -m app.seed

The demo generations are synthesised for real, so the library is not empty and
the player has something to play. If the speech service is unreachable the
account is still created and the script says so rather than pretending.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app import voices as catalog
from app.database import SessionLocal, init_db
from app.models import Chunk, Generation, GenerationStatus, User
from app.security import hash_password
from app.services import chunker, synth
from app.services.normaliser import normalise

DEMO_EMAIL = "demo@nawa.app"
DEMO_PASSWORD = "nawademo2026"

DEMO_SCRIPTS: list[tuple[str, str, str]] = [
    (
        "Quarterly numbers",
        "en-US-AriaNeural",
        "Last quarter we raised Rs 2.5 crore at a valuation of $14 million. "
        "Our average order is now Rs 1,850, up 12.5 percent, and 40 percent of "
        "customers come back within 90 days.",
    ),
    (
        "Urdu sample",
        "ur-PK-UzmaNeural",
        "یہ آواز کا ایک نمونہ ہے۔ ہم نے 1,50,000 روپے کا بجٹ منظور کیا تھا، "
        "اور یہ کام 15/11/2026 تک مکمل ہوگا۔",
    ),
    (
        "Product walkthrough",
        "en-GB-SoniaNeural",
        "Nawa reads what you meant, not what you typed. Order No. 42 ships on "
        "2026-11-15, costs $1,299 excluding 18% tax, and weighs 2.4 kilograms.",
    ),
]


def _build(db, user: User, title: str, voice_id: str, text: str) -> bool:
    voice = catalog.get_voice(voice_id)
    prepared = normalise(text)
    texts = chunker.split(prepared)

    try:
        parts = asyncio.run(synth.synthesize(texts, voice=voice_id))
    except synth.SynthesisError as exc:
        print(f"  ! could not synthesise '{title}': {exc}")
        return False

    generation = Generation(
        user_id=user.id,
        title=title,
        text=text,
        normalised_text=prepared,
        voice=voice_id,
        voice_label=f"{voice.label} — {voice.language}" if voice else voice_id,
        status=GenerationStatus.COMPLETED,
        char_count=len(prepared),
        chunk_count=len(parts),
        duration_ms=sum(p.duration_ms for p in parts),
        completed_at=datetime.now(UTC),
    )
    db.add(generation)
    db.flush()

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
    db.commit()
    print(f"  + {title}: {len(parts)} chunks, {generation.duration_ms} ms")
    return True


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None:
            user = User(
                email=DEMO_EMAIL,
                password_hash=hash_password(DEMO_PASSWORD),
                display_name="Demo",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"created demo account: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        else:
            print(f"demo account already exists: {DEMO_EMAIL}")

        existing = db.scalar(select(Generation).where(Generation.user_id == user.id).limit(1))
        if existing is not None:
            print("demo generations already present, nothing to do")
            return 0

        print("synthesising demo generations…")
        made = sum(_build(db, user, *script) for script in DEMO_SCRIPTS)
        if made == 0:
            print("no demo audio was created — the speech service was unreachable")
            return 1
        print(f"done: {made} of {len(DEMO_SCRIPTS)} demo generations ready")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
