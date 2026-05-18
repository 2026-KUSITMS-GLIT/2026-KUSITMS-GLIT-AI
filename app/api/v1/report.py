"""리포트 생성 실험 라우터 — ``/v1/reports/*``.

실제 서비스 레이어를 호출하는 실험·개발 경로.
검증이 끝나면 ``/api/reports/*`` 핸들러 본문을 이쪽 service 호출로 교체하면 운영 전환 완료.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.report import (
    AiCareerBrandingResponse,
    AiCareerHighlightsResponse,
    AiCareerInterviewRequest,
    AiCareerInterviewResponse,
    AiCareerNarrativeResponse,
    AiCareerStrengthsResponse,
    AiMiniReportResponse,
    AiReportRequest,
)
from app.services import report as report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/mini", response_model=AiMiniReportResponse)
async def create_mini_report(req: AiReportRequest) -> AiMiniReportResponse:
    return await report_service.run_mini(req)


@router.post("/career/branding", response_model=AiCareerBrandingResponse)
async def create_career_branding(req: AiReportRequest) -> AiCareerBrandingResponse:
    return await report_service.run_branding(req)


@router.post("/career/narrative", response_model=AiCareerNarrativeResponse)
async def create_career_narrative(req: AiReportRequest) -> AiCareerNarrativeResponse:
    return await report_service.run_narrative(req)


@router.post("/career/strengths", response_model=AiCareerStrengthsResponse)
async def create_career_strengths(req: AiReportRequest) -> AiCareerStrengthsResponse:
    return await report_service.run_strengths(req)


@router.post("/career/highlights", response_model=AiCareerHighlightsResponse)
async def create_career_highlights(req: AiReportRequest) -> AiCareerHighlightsResponse:
    return await report_service.run_highlights(req)


@router.post("/career/interview", response_model=AiCareerInterviewResponse)
async def create_career_interview(
    req: AiCareerInterviewRequest,
) -> AiCareerInterviewResponse:
    return await report_service.run_interview(req)
