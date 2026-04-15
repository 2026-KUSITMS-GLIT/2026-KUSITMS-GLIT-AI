"""Internal-token auth for Spring Boot ↔ AI service."""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    """Verify the internal token. Use as a FastAPI dependency.

    Spring Boot attaches ``X-Internal-Token: <shared secret>`` to every request.
    """
    settings = get_settings()
    if x_internal_token is None or not hmac.compare_digest(
        x_internal_token, settings.internal_api_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing internal token",
        )
