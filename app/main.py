"""FastAPI application entrypoint.

Start locally:
    uv run uvicorn app.main:app --reload

Production (inside container):
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app import __version__
from app.api.v1 import health
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger = get_logger("app.main")
    settings = get_settings()
    logger.info("glit-ai starting version=%s env=%s", __version__, settings.app_env)
    yield
    logger.info("glit-ai stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Glit AI Service",
        description=(
            "Glit 커리어 기록 서비스의 AI 전담 레포. "
            "Spring Boot 백엔드와 내부 토큰으로 통신하는 Stateless 서비스."
        ),
        version=__version__,
        default_response_class=ORJSONResponse,
        docs_url="/docs" if not settings.is_prod else None,
        redoc_url="/redoc" if not settings.is_prod else None,
        openapi_url="/openapi.json" if not settings.is_prod else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers — 새 기능은 app/api/v1/<feature>.py 만들어서 여기에 include_router.
    app.include_router(health.router)

    return app


app = create_app()
