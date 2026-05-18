"""리포트 생성 서비스 v1 baseline — Claude API 구현 예정.

각 run_* 함수 본문을 LLMClient 호출 로직으로 교체한다.
"""

from __future__ import annotations

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

_TODO = "[TODO: Claude API 구현 예정]"


async def run_mini(req: AiReportRequest) -> AiMiniReportResponse:
    return AiMiniReportResponse(
        activity_summary=_TODO,
        next_focus_point=_TODO,
    )


async def run_branding(req: AiReportRequest) -> AiCareerBrandingResponse:
    return AiCareerBrandingResponse(
        branding_statement=_TODO,
        branding_pattern=_TODO,
    )


async def run_narrative(req: AiReportRequest) -> AiCareerNarrativeResponse:
    return AiCareerNarrativeResponse(narrative_summary=_TODO)


async def run_strengths(req: AiReportRequest) -> AiCareerStrengthsResponse:
    ids = [r.star_record_id for r in req.records[:2]]
    record_ids = ids if len(ids) >= 2 else ids * 2
    return AiCareerStrengthsResponse(
        strengths=[
            StrengthItem(title=_TODO, description=_TODO, evidence_ids=record_ids),
            StrengthItem(title=_TODO, description=_TODO, evidence_ids=record_ids),
        ]
    )


async def run_highlights(req: AiReportRequest) -> AiCareerHighlightsResponse:
    return AiCareerHighlightsResponse(experience_highlights=[_TODO, _TODO])


async def run_interview(req: AiCareerInterviewRequest) -> AiCareerInterviewResponse:
    evidence_ids = req.evidence_ids[:2] if len(req.evidence_ids) >= 2 else req.evidence_ids
    return AiCareerInterviewResponse(
        interview_questions=[
            InterviewQuestion(question=_TODO, evidence_ids=evidence_ids),
            InterviewQuestion(question=_TODO, evidence_ids=evidence_ids),
        ]
    )
