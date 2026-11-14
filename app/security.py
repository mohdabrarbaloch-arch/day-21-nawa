"""Password hashing and JWT handling.

Two kinds of token exist, and they are deliberately not interchangeable:

* an access token is a full session and carries a "type" claim;
* an audio token is a short-lived capability that can only fetch one
  generation's audio. It is what goes in an <audio src> URL, because a URL
  ends up in browser history and server logs and should not be a session.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

_ACCESS = "access"
_AUDIO = "audio"

# passlib is used for verification so existing hashes stay readable if the
# project later moves to argon2. bcrypt is called directly for hashing
# because passlib's bcrypt backend is not compatible with bcrypt>=4.1.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    """Hash a password with bcrypt at cost 12."""
    if not password:
        raise ValueError("password must not be empty")
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        # bcrypt silently truncates past 72 bytes, which would make two
        # different long passwords interchangeable.
        raise ValueError("password must be at most 72 bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    encoded = password.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed hash in the row: treat as a failed login, never a 500.
        return False


def _encode(payload: dict, *, expires: timedelta) -> str:
    now = datetime.now(UTC)
    body = {**payload, "iat": int(now.timestamp()), "exp": int((now + expires).timestamp())}
    return jwt.encode(body, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int) -> str:
    return _encode(
        {"sub": str(user_id), "type": _ACCESS},
        expires=timedelta(minutes=settings.access_token_minutes),
    )


def create_audio_token(user_id: int, generation_id: int) -> str:
    return _encode(
        {"sub": str(user_id), "type": _AUDIO, "gen": generation_id},
        expires=timedelta(minutes=settings.audio_token_minutes),
    )


def _decode(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


def decode_access_token(token: str) -> int | None:
    """Return the user id, or None if the token is invalid or the wrong type."""
    try:
        payload = _decode(token)
    except JWTError:
        return None
    if payload.get("type") != _ACCESS:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None


def decode_audio_token(token: str, generation_id: int) -> int | None:
    """Return the user id if this capability is valid for that generation."""
    try:
        payload = _decode(token)
    except JWTError:
        return None
    if payload.get("type") != _AUDIO:
        return None
    if payload.get("gen") != generation_id:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
