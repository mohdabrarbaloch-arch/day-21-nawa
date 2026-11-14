"""Application factory: middleware, routers, storage, static UI."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import init_db
from app.limiter import limiter
from app.routers import auth, generations, pronunciations, voices
from app.services import synth

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("nawa")

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    logger.info(
        "Nawa %s starting in %s mode on %s",
        settings.app_version,
        settings.environment,
        settings.database_url.split("://")[0],
    )
    yield
    # Let in-flight synthesis finish rather than killing the loop mid-request.
    logger.info("Nawa shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Nawa API",
        version=settings.app_version,
        description=(
            "Text-to-speech studio. Turns written text into speech, with the "
            "numbers rewritten into the words a person would actually say."
        ),
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.state.limiter = limiter

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # noqa: ANN001, ANN202
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        # The studio is one page with inline styles; everything else is same-origin.
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "media-src 'self' blob:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'",
        )
        return response

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Take a breath and try again shortly."},
            headers={"Retry-After": "60"},
        )

    @app.exception_handler(synth.SynthesisError)
    async def synthesis_error_handler(_request: Request, exc: synth.SynthesisError) -> JSONResponse:
        # Upstream speech service trouble is a gateway problem, not our bug.
        logger.warning("synthesis failed: %s", exc)
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(voices.router, prefix="/api", tags=["voices"])
    app.include_router(generations.router, prefix="/api/generations", tags=["generations"])
    app.include_router(pronunciations.router, prefix="/api/pronunciations", tags=["pronunciations"])

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str | int]:
        return {
            "status": "ok",
            "version": settings.app_version,
            "environment": settings.environment,
            "voices": len(voices.all_voices()),
        }

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="studio")

    return app


app = create_app()
