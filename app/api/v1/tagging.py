"""POST /v1/tagging — STAR 심화 기록에 대한 세부 역량 태그 추출 (실험 경로).

cutover 전 실험·검증용 경로. Spring 이 호출하기로 한 안정 경로는 ``POST /api/tagging``
(별도 라우터, 더미 응답) 이며, v1_baseline 이 확정되면 안정 경로의 본문을 이쪽 service
호출로 교체하는 cutover 가 일어난다.

라우터 책임:
    - 요청 스키마 검증 (FastAPI 가 ``TaggingRequest`` 로 처리)
    - ``LLMClient`` 싱글턴을 ``request.state`` 에서 꺼내 service 호출
    - 도메인 예외 → HTTP 상태코드 매핑
    - 실패 단계만 ``tagging.failed`` 로 로깅 (성공 로그는 service 가 찍음)
    - STAR 본문은 절대 로그/응답에 echo 하지 않는다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.tagging import TaggingRequest, TaggingResponse
from app.services._clients.exceptions import (
    LLMAuthError,
    LLMBadRequestError,
    LLMRateLimitedError,
    LLMUpstreamUnavailableError,
)
from app.services._clients.llm_client import LLMClient
from app.services.tagging import run as tagging_run
from app.services.tagging.exceptions import TaggingValidationError

logger = get_logger(__name__)

router = APIRouter(tags=["tagging"])


def get_llm_client(request: Request) -> LLMClient:
    """lifespan 에서 yield 한 ``LLMClient`` 싱글턴을 dependency 로 노출한다.

    main.py 의 ``lifespan`` 이 ``yield {"llm_client": llm_client}`` 로 starlette ASGI
    lifespan state 에 박아 두면, 각 요청의 ``request.state.llm_client`` 로 접근 가능.
    이 함수는 그 접근을 한 곳으로 모아 두어 테스트 시 ``dependency_overrides`` 로 mock
    주입을 가능케 한다.
    """
    client = request.state.llm_client
    assert isinstance(client, LLMClient), "lifespan 에서 llm_client 가 주입되어야 한다"
    return client


@router.post(
    "/tagging",
    summary="STAR 심화 기록 세부 역량 태그 추출 (실험 경로)",
    description=(
        "v1_baseline 프롬프트로 LLM 을 호출해 66개 태그 풀에서 1~3개를 추출한다. "
        "Spring 이 호출할 안정 경로는 ``/api/tagging`` (별도). 이 경로는 cutover 전 검증용."
    ),
    response_model=TaggingResponse,
    response_model_by_alias=True,
)
async def tagging_v1(
    req: TaggingRequest,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> TaggingResponse:
    settings = get_settings()
    log_ctx = {
        "job_role": req.job_role.value,
        "primary_category": req.selected_competency.value,
    }
    try:
        return await tagging_run(req, llm, settings.anthropic_model)
    except TaggingValidationError as exc:
        logger.warning(
            "tagging.failed",
            extra={**log_ctx, "stage": "validation", "reason": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "TAG_EXTRACTION_FAILED",
                "message": "두 번의 시도 모두 응답이 형식을 만족하지 못했습니다.",
            },
        ) from exc
    except LLMRateLimitedError as exc:
        logger.warning(
            "tagging.failed",
            extra={**log_ctx, "stage": "llm", "error_type": "rate_limited"},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM rate limited",
        ) from exc
    except (LLMUpstreamUnavailableError, LLMBadRequestError, LLMAuthError) as exc:
        # Auth/BadRequest 도 외부에는 ``upstream unavailable`` 로 마스킹한다.
        # (``LLMAuthError`` docstring 참고 — 키 노출 회피)
        logger.warning(
            "tagging.failed",
            extra={**log_ctx, "stage": "llm", "error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM upstream unavailable",
        ) from exc
