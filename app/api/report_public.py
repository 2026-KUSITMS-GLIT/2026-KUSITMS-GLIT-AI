"""리포트 생성 안정 라우터 — ``/api/reports/*``.

Spring이 호출하는 최종 안정 경로. 현재는 요청 스키마 검증 후 고정 더미 응답 반환.
cutover 시 각 핸들러 본문을 ``report_service.run_*`` 호출로 교체하면 운영 전환 완료.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import require_internal_token
from app.schemas.report import (
    AiCareerBrandingResponse,
    AiCareerHighlightsResponse,
    AiCareerInterviewRequest,
    AiCareerInterviewResponse,
    AiCareerNarrativeResponse,
    AiCareerStrengthsResponse,
    AiMiniReportResponse,
    AiReportRequest,
    InterviewQuestion,
    StrengthItem,
)

router = APIRouter(
    prefix="/api/reports",
    tags=["reports"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("/mini", response_model=AiMiniReportResponse)
async def create_mini_report(req: AiReportRequest) -> AiMiniReportResponse:
    return AiMiniReportResponse(
        activity_summary=(
            f"{req.competency_stats.total_count}개의 기록을 분석했어요. "
            "다양한 프로젝트에서 역량을 꾸준히 쌓아오고 있습니다."
        ),
        next_focus_point="다양한 역량 영역의 경험을 골고루 기록해보세요.",
    )


@router.post("/career/branding", response_model=AiCareerBrandingResponse)
async def create_career_branding(req: AiReportRequest) -> AiCareerBrandingResponse:
    return AiCareerBrandingResponse(
        branding_statement="복잡한 문제를 구조로 풀어내는 '설계형 인재'입니다.",
        branding_pattern="복잡한 상황에서 먼저 구조를 정의하는 행동 방식",
    )


@router.post("/career/narrative", response_model=AiCareerNarrativeResponse)
async def create_career_narrative(req: AiReportRequest) -> AiCareerNarrativeResponse:
    return AiCareerNarrativeResponse(
        narrative_summary=(
            "여러 프로젝트를 거치며 각 과제를 먼저 구조화하고 실행하는 방식을 "
            "일관되게 유지해왔습니다. 협업 상황에서도 전체 흐름을 먼저 정의한 뒤 "
            "팀원과 역할을 나누는 방식으로 성과를 만들어냈습니다."
        ),
    )


@router.post("/career/strengths", response_model=AiCareerStrengthsResponse)
async def create_career_strengths(req: AiReportRequest) -> AiCareerStrengthsResponse:
    record_ids = [r.star_record_id for r in req.records[:2]]
    return AiCareerStrengthsResponse(
        strengths=[
            StrengthItem(
                title="구조 먼저 잡는 기획력",
                description="요구사항이 복잡할수록 전체 흐름을 먼저 정의하고 실행해요.",
                evidence_ids=record_ids,
            ),
            StrengthItem(
                title="이해관계자 조율 능력",
                description="복수의 의견이 충돌할 때 공통 기준을 만들어 합의를 이끌어요.",
                evidence_ids=record_ids,
            ),
        ]
    )


@router.post("/career/highlights", response_model=AiCareerHighlightsResponse)
async def create_career_highlights(req: AiReportRequest) -> AiCareerHighlightsResponse:
    return AiCareerHighlightsResponse(
        experience_highlights=[
            "이해관계자 요구가 충돌하는 상황에서 PRD를 작성해 단기간에 합의를 이끌어냈습니다.",
            "프로젝트 구조를 먼저 정의해 팀원과 역할을 나누고 일정 내 목표를 달성했습니다.",
        ]
    )


@router.post("/career/interview", response_model=AiCareerInterviewResponse)
async def create_career_interview(
    req: AiCareerInterviewRequest,
) -> AiCareerInterviewResponse:
    evidence_ids = req.evidence_ids[:2] if len(req.evidence_ids) >= 2 else req.evidence_ids
    return AiCareerInterviewResponse(
        interview_questions=[
            InterviewQuestion(
                question=(
                    "단기간에 합의를 이끌어냈다고 하셨는데, "
                    "구체적으로 얼마 만이었고 어떤 트레이드오프가 있었나요?"
                ),
                evidence_ids=evidence_ids,
            ),
            InterviewQuestion(
                question=(
                    "구조를 먼저 정의한다고 하셨는데, "
                    "그 구조가 틀렸다고 느꼈을 때는 어떻게 대응하셨나요?"
                ),
                evidence_ids=evidence_ids,
            ),
        ]
    )
