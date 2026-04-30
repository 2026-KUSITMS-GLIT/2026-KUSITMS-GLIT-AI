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

from app import __version__
from app.api import health
from app.api.v1 import router as v1_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """앱 전체 생명주기 훅.

    **startup** — 로깅을 먼저 초기화하고 ``Settings`` 를 로드해 검증한다.
    prod 환경에서 ``INTERNAL_API_TOKEN`` 이 기본값이면 ``Settings`` 가
    ``ValidationError`` 를 던지며, 이 경우 앱은 부팅되지 않는다 (ASGI lifespan
    예외는 곧 서버 기동 실패로 이어짐)

    **shutdown** — 현재는 종료 로그만 남긴다. 외부 클라이언트(AI provider HTTP
    세션, Redis 풀 등)를 붙이게 되면 ``yield`` 뒤 구간에서 ``await client.aclose()``
    형태로 정리 훅을 추가한다.
    """
    configure_logging()
    logger = get_logger("app.main")
    settings = get_settings()
    logger.info(
        "app.started",
        extra={
            "version": __version__,
            "env": settings.app_env,
            "log_level": settings.log_level,
        },
    )
    yield
    # shutdown hooks — 외부 리소스가 생기면 여기에 정리 코드를 추가한다.
    logger.info("app.stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Glit AI Service",
        description=(
            "Glit 커리어 기록 서비스의 AI 전담 레포. "
            "Spring Boot 백엔드와 내부 토큰으로 통신하는 Stateless 서비스."
        ),
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Routers.
    # - health: 인프라 probe. 토큰 인증 예외, 버전 prefix 없음.
    # - v1_router: 비즈니스 API. prefix="/v1" + X-Internal-Token 전역 보호.
    #   새 기능은 app/api/v1/<feature>.py 만들고 app/api/v1/__init__.py 의
    #   include_router 목록에 한 줄 추가하는 식으로 붙인다 (여기는 건드리지 않음).
    # CORS 미들웨어는 의도적으로 미포함 — 서버 간 통신이므로 불필요.
    app.include_router(health.router)
    app.include_router(v1_router)

    return app


app = create_app()
