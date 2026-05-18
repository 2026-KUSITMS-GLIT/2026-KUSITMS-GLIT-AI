"""리포트 생성 실험 라우터 — ``/v1/reports/*``.

실제 서비스 레이어를 호출하는 실험·개발 경로.
검증이 끝나면 ``/api/reports/*`` 핸들러 본문을 이쪽 service 호출로 교체하면 운영 전환 완료.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.report import (
    AiCareerBrandingResponse,
    AiCareerHighlightsResponse,
    AiCareerNarrativeResponse,
    AiCareerStrengthsAndInterviewResponse,
    AiMiniReportResponse,
    AiReportRequest,
)
from app.services import report as report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/mini", response_model=AiMiniReportResponse, summary="미니 리포트 생성")
async def create_mini_report(req: AiReportRequest) -> AiMiniReportResponse:
    return await report_service.run_mini(req)


@router.post(
    "/career/branding", response_model=AiCareerBrandingResponse, summary="커리어 브랜딩 생성"
)
async def create_career_branding(req: AiReportRequest) -> AiCareerBrandingResponse:
    return await report_service.run_branding(req)


@router.post(
    "/career/narrative", response_model=AiCareerNarrativeResponse, summary="커리어 내러티브 생성"
)
async def create_career_narrative(req: AiReportRequest) -> AiCareerNarrativeResponse:
    return await report_service.run_narrative(req)


@router.post(
    "/career/strengths-and-interview",
    response_model=AiCareerStrengthsAndInterviewResponse,
    summary="커리어 강점 및 면접 질문 생성",
)
async def create_career_strengths_and_interview(
    req: AiReportRequest,
) -> AiCareerStrengthsAndInterviewResponse:
    return await report_service.run_strengths_and_interview(req)


@router.post(
    "/career/highlights",
    response_model=AiCareerHighlightsResponse,
    summary="커리어 하이라이트 생성",
)
async def create_career_highlights(req: AiReportRequest) -> AiCareerHighlightsResponse:
    return await report_service.run_highlights(req)
