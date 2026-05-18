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
            "글릿님은 KOPLE, 밋업 프로젝트 등 복수의 프로젝트를 동시에 진행하며 "
            "각 과제를 구조화하는 작업을 반복해왔어요. 특히 복잡한 요구사항이 주어졌을 때 "
            "먼저 전체 흐름을 정의하고 실행하는 방식이 기록 전반에서 일관되게 나타나요. "
            "설계 중 의문이 생기면 진행을 멈추고 재검토하는 패턴도 눈에 띄어요."
        ),
        next_focus_point=(
            "아직 협업·조율 영역 기록이 적어요. 팀원과 의견을 조율했던 경험이나 "
            "피드백을 주고받은 순간을 기록해보면 더 입체적인 커리어 서사가 만들어질 거예요."
        ),
    )


@router.post("/career/branding", response_model=AiCareerBrandingResponse)
async def create_career_branding(req: AiReportRequest) -> AiCareerBrandingResponse:
    return AiCareerBrandingResponse(
        branding_statement="글릿님은 복잡한 문제를 구조로 풀어내는 '설계형 기획자'입니다.",
        branding_pattern="복잡한 상황에서 먼저 구조를 정의하는 행동 방식",
    )


@router.post("/career/narrative", response_model=AiCareerNarrativeResponse)
async def create_career_narrative(req: AiReportRequest) -> AiCareerNarrativeResponse:
    return AiCareerNarrativeResponse(
        narrative_summary=(
            "글릿님은 복수의 프로젝트를 동시에 진행하면서도 각 과제를 먼저 구조화하고 "
            "실행하는 방식을 일관되게 유지해왔어요. 기획 중 설계적 의문이 생기면 진행을 "
            "멈추고 재검토하는 패턴이 반복되며, 이는 완성도에 대한 높은 기준을 반영해요. "
            "#기획_구조화와 #구조_개선이 다른 역량 태그보다 유독 많이 나온 건 이 방식의 증거예요."
        ),
    )


@router.post("/career/strengths", response_model=AiCareerStrengthsResponse)
async def create_career_strengths(req: AiReportRequest) -> AiCareerStrengthsResponse:
    ids = [r.star_record_id for r in req.records[:2]]
    record_ids = ids if len(ids) >= 2 else ids * 2
    return AiCareerStrengthsResponse(
        strengths=[
            StrengthItem(
                title="구조 먼저 잡는 기획력",
                description=(
                    "요구사항이 복잡할수록 전체 흐름을 먼저 정의하고 실행해요. "
                    "설계 중 의문이 생기면 멈추고 재검토하는 패턴이 일관돼요."
                ),
                evidence_ids=record_ids,
            ),
            StrengthItem(
                title="시스템으로 해결하는 협업",
                description=(
                    "커뮤니케이션 문제를 개인 노력이 아닌 구조와 규칙으로 풀려는 접근이 반복돼요."
                ),
                evidence_ids=record_ids,
            ),
        ]
    )


@router.post("/career/highlights", response_model=AiCareerHighlightsResponse)
async def create_career_highlights(req: AiReportRequest) -> AiCareerHighlightsResponse:
    return AiCareerHighlightsResponse(
        experience_highlights=[
            (
                "복수의 이해관계자 요구가 충돌하는 KOPLE 프로젝트에서, "
                "전체 흐름을 구조화해 PRD와 기능명세서를 단기간에 완성했습니다."
            ),
            (
                "설계 중 구조적 의문이 생겼을 때 진행을 멈추고 재검토함으로써, "
                "개발 착수 전 핵심 설계 이슈를 선제 해결했습니다."
            ),
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
                    "KOPLE 프로젝트에서 단기간에 완성했다고 하셨는데, "
                    "구체적으로 얼마 만이었고 어떤 트레이드오프가 있었나요?"
                ),
                evidence_ids=evidence_ids,
            ),
            InterviewQuestion(
                question="진행을 멈추고 재검토하는 판단을 팀원들에게 어떻게 설득하셨나요?",
                evidence_ids=evidence_ids,
            ),
        ]
    )
