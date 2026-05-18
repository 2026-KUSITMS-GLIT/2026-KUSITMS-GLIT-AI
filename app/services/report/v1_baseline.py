"""리포트 생성 서비스 v1 baseline — 더미 응답 반환."""

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


async def run_mini(req: AiReportRequest) -> AiMiniReportResponse:
    top_tags = ", ".join(req.competency_stats.top_detail_tags)
    # 가장 적게 기록된 역량 카테고리 → nextFocusPoint 제안 근거
    freq = req.competency_stats.primary_category_frequency
    low_category = min(freq, key=lambda c: c.count).category if freq else None
    next_point = (
        f"{low_category} 영역 기록이 아직 적어요. 관련 경험을 기록해보면 "
        "더 입체적인 커리어 서사가 만들어질 거예요."
        if low_category
        else "다양한 역량 영역의 경험을 골고루 기록해보세요."
    )
    return AiMiniReportResponse(
        activity_summary=(
            f"{req.competency_stats.total_count}개의 기록을 통해 {top_tags} 활동이 "
            "반복적으로 나타나고 있어요. 각 과제를 구조화하고 실행하는 방식이 "
            "기록 전반에 일관되게 드러납니다."
        ),
        next_focus_point=next_point,
    )


async def run_branding(req: AiReportRequest) -> AiCareerBrandingResponse:
    return AiCareerBrandingResponse(
        branding_statement="복잡한 문제를 구조로 풀어내는 실행형 인재입니다.",
        branding_pattern="문제 상황에서 먼저 전체 구조를 정의하고 실행하는 행동 방식",
    )


async def run_narrative(req: AiReportRequest) -> AiCareerNarrativeResponse:
    return AiCareerNarrativeResponse(
        narrative_summary=(
            "여러 프로젝트를 거치며 각 과제를 먼저 구조화하고 실행하는 방식을 "
            "일관되게 유지해왔습니다. 협업 상황에서도 전체 흐름을 먼저 정의한 뒤 "
            "팀원과 역할을 나누는 방식으로 성과를 만들어냈습니다."
        ),
    )


async def run_strengths(req: AiReportRequest) -> AiCareerStrengthsResponse:
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


async def run_highlights(req: AiReportRequest) -> AiCareerHighlightsResponse:
    return AiCareerHighlightsResponse(
        experience_highlights=[
            "이해관계자 요구가 충돌하는 상황에서 PRD를 작성해 단기간에 합의를 이끌어냈습니다.",
            "프로젝트 구조를 먼저 정의해 팀원과 역할을 나누고 일정 내 목표를 달성했습니다.",
        ]
    )


async def run_interview(req: AiCareerInterviewRequest) -> AiCareerInterviewResponse:
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
