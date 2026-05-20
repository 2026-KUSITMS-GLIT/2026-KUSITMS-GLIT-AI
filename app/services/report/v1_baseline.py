"""리포트 생성 서비스 v1 baseline — Claude API 구현 예정.

각 run_* 함수 본문을 LLMClient 호출 로직으로 교체한다.
"""

from __future__ import annotations

from app.schemas.report import (
    AiCareerBrandingResponse,
    AiCareerHighlightsResponse,
    AiCareerNarrativeResponse,
    AiCareerStrengthsAndInterviewResponse,
    AiMiniReportResponse,
    AiReportRequest,
    InterviewQuestion,
    StrengthItem,
)
from app.services._clients.llm_client import LLMClient
from app.services.report._compute import (
    build_evidences,
    competency_frequency,
    top_detail_tag_stats,
    top_detail_tags,
)

_TODO = "[TODO: Claude API 구현 예정]"
_TODO_SHORT = "[TODO]"  # max_length 제약이 있는 필드용


async def run_mini(req: AiReportRequest, llm: LLMClient, model: str) -> AiMiniReportResponse:
    return AiMiniReportResponse(
        activity_summary=_TODO,
        next_focus_point=_TODO,
        competency_frequency=competency_frequency(req.records),
        top_detail_tags=top_detail_tags(req.records),
    )


async def run_branding(
    req: AiReportRequest, llm: LLMClient, model: str
) -> AiCareerBrandingResponse:
    return AiCareerBrandingResponse(
        branding_statement=_TODO,
        branding_pattern=_TODO,
        top_detail_tags=top_detail_tag_stats(req.records),
    )


async def run_narrative(
    _req: AiReportRequest, llm: LLMClient, model: str
) -> AiCareerNarrativeResponse:
    return AiCareerNarrativeResponse(narrative_summary=_TODO)


async def run_strengths_and_interview(
    req: AiReportRequest, llm: LLMClient, model: str
) -> AiCareerStrengthsAndInterviewResponse:
    record_ids = [r.star_record_id for r in req.records[:2]]
    evidences = build_evidences(req, record_ids)
    return AiCareerStrengthsAndInterviewResponse(
        strengths=[
            StrengthItem(title=_TODO_SHORT, description=_TODO, evidences=evidences),
            StrengthItem(title=_TODO_SHORT, description=_TODO, evidences=evidences),
        ],
        interview_questions=[
            InterviewQuestion(question=_TODO, evidences=evidences),
            InterviewQuestion(question=_TODO, evidences=evidences),
        ],
    )


async def run_highlights(
    _req: AiReportRequest, llm: LLMClient, model: str
) -> AiCareerHighlightsResponse:
    return AiCareerHighlightsResponse(experience_highlights=[_TODO, _TODO])
