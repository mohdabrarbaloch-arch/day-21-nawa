"""Rate limiter instance.

Lives in its own module so routers can decorate handlers without importing
``app.main``, which imports the routers. Same reason the database session is in
its own module.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings


def client_key(request: Request) -> str:
    return get_remote_address(request)


limiter = Limiter(key_func=client_key, enabled=settings.rate_limit_enabled)
