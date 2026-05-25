"""리포트 생성 실험 라우터 — ``/v1/reports/*``.

실제 서비스 레이어를 호출하는 실험·개발 경로.
검증이 끝나면 ``/api/reports/*`` 핸들러 본문을 이쪽 service 호출로 교체하면 운영 전환 완료.
"""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import require_internal_token
from app.schemas.report import (
    AiCareerBrandingResponse,
    AiCareerHighlightsResponse,
    AiCareerNarrativeResponse,
    AiCareerStrengthsAndInterviewResponse,
    AiMiniReportResponse,
    AiReportRequest,
)
from app.services import report as report_service
from app.services._clients.exceptions import (
    LLMAuthError,
    LLMBadRequestError,
    LLMRateLimitedError,
    LLMUpstreamUnavailableError,
)
from app.services._clients.llm_client import LLMClient
from app.services.report.exceptions import ReportValidationError

logger = get_logger(__name__)

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_internal_token)],
)

_LLM_ERRORS = (LLMRateLimitedError, LLMUpstreamUnavailableError, LLMBadRequestError, LLMAuthError)


def get_llm_client(request: Request) -> LLMClient:
    """lifespan 에서 yield 한 ``LLMClient`` 싱글턴을 dependency 로 노출한다."""
    client = getattr(request.state, "llm_client", None)
    if not isinstance(client, LLMClient):
        raise RuntimeError("lifespan 에서 llm_client 가 올바르게 주입되어야 한다")
    return client


def _handle_llm_exc(exc: Exception) -> NoReturn:
    if isinstance(exc, LLMRateLimitedError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM rate limited",
        ) from exc
    if isinstance(exc, LLMUpstreamUnavailableError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM upstream unavailable",
        ) from exc
    if isinstance(exc, LLMAuthError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM auth configuration error",
        ) from exc
    if isinstance(exc, LLMBadRequestError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="LLM request was rejected",
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected LLM error",
    ) from exc


@router.post("/mini", response_model=AiMiniReportResponse, summary="미니 리포트 생성")
async def create_mini_report(
    req: AiReportRequest,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> AiMiniReportResponse:
    settings = get_settings()
    try:
        return await report_service.run_mini(req, llm, settings.anthropic_model)
    except ReportValidationError as exc:
        logger.warning("report.mini.failed", extra={"stage": "validation", "reason": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "REPORT_GENERATION_FAILED",
                "message": "두 번의 시도 모두 응답이 형식을 만족하지 못했습니다.",
            },
        ) from exc
    except _LLM_ERRORS as exc:
        _handle_llm_exc(exc)


@router.post(
    "/career/branding", response_model=AiCareerBrandingResponse, summary="커리어 브랜딩 생성"
)
async def create_career_branding(
    req: AiReportRequest,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> AiCareerBrandingResponse:
    settings = get_settings()
    try:
        return await report_service.run_branding(req, llm, settings.anthropic_model)
    except ReportValidationError as exc:
        logger.warning("report.branding.failed", extra={"stage": "validation", "reason": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "REPORT_GENERATION_FAILED",
                "message": "두 번의 시도 모두 응답이 형식을 만족하지 못했습니다.",
            },
        ) from exc
    except _LLM_ERRORS as exc:
        _handle_llm_exc(exc)


@router.post(
    "/career/narrative", response_model=AiCareerNarrativeResponse, summary="커리어 내러티브 생성"
)
async def create_career_narrative(
    req: AiReportRequest,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> AiCareerNarrativeResponse:
    settings = get_settings()
    try:
        return await report_service.run_narrative(req, llm, settings.anthropic_model)
    except ReportValidationError as exc:
        logger.warning("report.narrative.failed", extra={"stage": "validation", "reason": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "REPORT_GENERATION_FAILED",
                "message": "두 번의 시도 모두 응답이 형식을 만족하지 못했습니다.",
            },
        ) from exc
    except _LLM_ERRORS as exc:
        _handle_llm_exc(exc)


@router.post(
    "/career/strengths-and-interview",
    response_model=AiCareerStrengthsAndInterviewResponse,
    summary="커리어 강점 및 면접 질문 생성",
)
async def create_career_strengths_and_interview(
    req: AiReportRequest,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> AiCareerStrengthsAndInterviewResponse:
    settings = get_settings()
    try:
        return await report_service.run_strengths_and_interview(req, llm, settings.anthropic_model)
    except ReportValidationError as exc:
        logger.warning("report.strengths.failed", extra={"stage": "validation", "reason": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "REPORT_GENERATION_FAILED",
                "message": "두 번의 시도 모두 응답이 형식을 만족하지 못했습니다.",
            },
        ) from exc
    except _LLM_ERRORS as exc:
        _handle_llm_exc(exc)


@router.post(
    "/career/highlights",
    response_model=AiCareerHighlightsResponse,
    summary="커리어 하이라이트 생성",
)
async def create_career_highlights(
    req: AiReportRequest,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> AiCareerHighlightsResponse:
    settings = get_settings()
    try:
        return await report_service.run_highlights(req, llm, settings.anthropic_model)
    except ReportValidationError as exc:
        logger.warning(
            "report.highlights.failed", extra={"stage": "validation", "reason": str(exc)}
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "REPORT_GENERATION_FAILED",
                "message": "두 번의 시도 모두 응답이 형식을 만족하지 못했습니다.",
            },
        ) from exc
    except _LLM_ERRORS as exc:
        _handle_llm_exc(exc)
