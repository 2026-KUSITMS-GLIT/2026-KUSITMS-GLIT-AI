"""리포트 생성 요청/응답 스키마."""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

from app.schemas.common import JobRole, UserStatus

__all__ = [
    "AiCareerBrandingResponse",
    "AiCareerHighlightsResponse",
    "AiCareerInterviewRequest",
    "AiCareerInterviewResponse",
    "AiCareerNarrativeResponse",
    "AiCareerStrengthsResponse",
    "AiMiniReportResponse",
    "AiReportRequest",
    "JobRole",
    "UserStatus",
]


class _CamelModel(BaseModel):
    model_config = {"alias_generator": to_camel, "populate_by_name": True}


# ── Sub-models ─────────────────────────────────────────────────────────────


class ScrumData(_CamelModel):
    project_name: str
    content: str


class StarRecord(_CamelModel):
    star_record_id: int
    situation_task: str = Field(max_length=300)
    action: str = Field(max_length=300)
    result: str = Field(max_length=300)
    scrum: ScrumData
    completed_at: str


class CategoryFrequency(_CamelModel):
    category: str
    count: int


class RecordPeriod(_CamelModel):
    from_: str = Field(alias="from", serialization_alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$")
    to: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class CompetencyStats(_CamelModel):
    primary_category_frequency: list[CategoryFrequency]
    top_detail_tags: list[str] = Field(max_length=3)
    record_period: RecordPeriod
    total_count: int


# ── Requests ───────────────────────────────────────────────────────────────


class AiReportRequest(_CamelModel):
    job: JobRole
    status: UserStatus
    records: list[StarRecord]
    competency_stats: CompetencyStats


class AiCareerInterviewRequest(AiReportRequest):
    evidence_ids: list[int]


# ── Responses ──────────────────────────────────────────────────────────────


class AiMiniReportResponse(_CamelModel):
    activity_summary: str = Field(max_length=300)
    next_focus_point: str = Field(max_length=150)


class AiCareerBrandingResponse(_CamelModel):
    branding_statement: str = Field(max_length=60)
    branding_pattern: str


class AiCareerNarrativeResponse(_CamelModel):
    narrative_summary: str = Field(max_length=300)


class StrengthItem(_CamelModel):
    title: str = Field(max_length=15)
    description: str = Field(max_length=100)
    evidence_ids: list[int] = Field(min_length=2, max_length=3)


class AiCareerStrengthsResponse(_CamelModel):
    strengths: list[StrengthItem] = Field(min_length=2, max_length=3)


class AiCareerHighlightsResponse(_CamelModel):
    experience_highlights: list[str] = Field(min_length=2, max_length=3)


class InterviewQuestion(_CamelModel):
    question: str = Field(max_length=100)
    evidence_ids: list[int]


class AiCareerInterviewResponse(_CamelModel):
    interview_questions: list[InterviewQuestion] = Field(min_length=2, max_length=3)
