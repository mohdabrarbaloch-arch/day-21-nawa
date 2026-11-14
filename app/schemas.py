"""Request and response shapes.

Every field that ends up in a prompt, a filename or a URL is constrained here
rather than checked in a handler.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.config import settings


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=72)
    display_name: str = Field(default="", max_length=80)

    @field_validator("password")
    @classmethod
    def _strength(cls, value: str) -> str:
        if value.lower() in {"password12", "1234567890", "qwertyuiop"}:
            raise ValueError("that password is too common")
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("password needs at least one letter and one digit")
        return value

    @field_validator("display_name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        return value.strip()


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


class GenerationCreate(BaseModel):
    text: str = Field(min_length=1, max_length=settings.max_text_chars)
    title: str = Field(default="", max_length=140)
    voice: str = Field(default="en-US-AriaNeural", max_length=80)
    rate: float = Field(default=1.0, ge=0.5, le=2.0)
    pitch: float = Field(default=0.0, ge=-12.0, le=12.0)
    volume: float = Field(default=1.0, ge=0.1, le=2.0)
    normalise: bool = True

    @field_validator("text")
    @classmethod
    def _has_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value.strip()

    @field_validator("voice")
    @classmethod
    def _known_voice(cls, value: str) -> str:
        from app.voices import is_supported

        if not is_supported(value):
            raise ValueError("unknown voice")
        return value


class ChunkOut(BaseModel):
    index: int
    text: str
    duration_ms: int


class WordOut(BaseModel):
    start_ms: int
    end_ms: int
    text: str


class GenerationOut(BaseModel):
    id: int
    title: str
    voice: str
    voice_label: str
    rate: float
    pitch: float
    volume: float
    status: str
    error: str
    duration_ms: int
    char_count: int
    chunk_count: int
    created_at: datetime
    completed_at: datetime | None = None
    audio_url: str | None = None


class GenerationDetail(GenerationOut):
    text: str
    normalised_text: str
    chunks: list[ChunkOut] = []
    words: list[WordOut] = []


class GenerationListOut(BaseModel):
    items: list[GenerationOut]
    total: int


class PronunciationIn(BaseModel):
    written: str = Field(min_length=1, max_length=120)
    spoken: str = Field(min_length=1, max_length=200)

    @field_validator("written", "spoken")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class PronunciationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    written: str
    spoken: str
    enabled: bool


class PreviewIn(BaseModel):
    text: str = Field(min_length=1, max_length=settings.max_text_chars)
    voice: str = Field(default="en-US-AriaNeural", max_length=80)
    normalise: bool = True

    @field_validator("voice")
    @classmethod
    def _known_voice(cls, value: str) -> str:
        from app.voices import is_supported

        if not is_supported(value):
            raise ValueError("unknown voice")
        return value


class PreviewOut(BaseModel):
    before: str
    after: str
    chunks: list[str]
    estimated_seconds: float
    char_count: int


class UsageOut(BaseModel):
    used_today: int
    limit: int
    remaining: int
