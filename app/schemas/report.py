"""리포트 생성 요청/응답 스키마."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints
from pydantic.alias_generators import to_camel

from app.schemas.common import JobRole, UserStatus

__all__ = [
    "AiCareerBrandingResponse",
    "AiCareerHighlightsResponse",
    "AiCareerNarrativeResponse",
    "AiCareerStrengthsAndInterviewResponse",
    "AiMiniReportResponse",
    "AiReportRequest",
    "CompetencyCount",
    "DetailTagStat",
    "EvidenceItem",
    "InterviewQuestion",
    "JobRole",
    "StrengthItem",
    "UserStatus",
]


class _CamelModel(BaseModel):
    model_config = {"alias_generator": to_camel, "populate_by_name": True}


# ── Request sub-models ─────────────────────────────────────────────────────


class StarRecord(_CamelModel):
    star_record_id: int
    situation_task: str = Field(max_length=300)
    action: str = Field(max_length=300)
    result: str = Field(max_length=300)
    completed_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    competency: str
    detail_tags: list[str] = Field(min_length=1, max_length=3)


class ScrumItem(_CamelModel):
    project_name: str
    scrum_title: str
    content: str
    star_record_id: int | None = None


class ScrumsByDate(_CamelModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    scrums: list[ScrumItem]


class RecordPeriod(_CamelModel):
    from_: str = Field(alias="from", serialization_alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$")
    to: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


# ── Requests ───────────────────────────────────────────────────────────────


class AiReportRequest(_CamelModel):
    nickname: str
    job: JobRole
    status: UserStatus
    records: list[StarRecord]
    scrums_by_date: list[ScrumsByDate]
    record_period: RecordPeriod
    total_count: int


# ── Response sub-models ────────────────────────────────────────────────────


class CompetencyCount(_CamelModel):
    competency: str
    count: int


class DetailTagStat(_CamelModel):
    tag: str
    count: int


class EvidenceItem(_CamelModel):
    id: int
    project_name: str
    scrum_title: str
    created_at: str


# ── Responses ──────────────────────────────────────────────────────────────


class AiMiniReportResponse(_CamelModel):
    activity_summary: str = Field(max_length=300)
    next_focus_point: str = Field(max_length=150)
    competency_frequency: list[CompetencyCount]
    top_detail_tags: list[str]


class AiCareerBrandingResponse(_CamelModel):
    branding_statement: str = Field(max_length=60)
    branding_pattern: str
    top_detail_tags: list[DetailTagStat]


class AiCareerNarrativeResponse(_CamelModel):
    narrative_summary: str = Field(max_length=300)


class StrengthItem(_CamelModel):
    title: str = Field(max_length=15)
    description: str = Field(max_length=100)
    evidences: list[EvidenceItem]


_Highlight = Annotated[str, StringConstraints(max_length=80)]


class AiCareerHighlightsResponse(_CamelModel):
    experience_highlights: list[_Highlight] = Field(min_length=2, max_length=3)


class InterviewQuestion(_CamelModel):
    question: str = Field(max_length=100)
    evidences: list[EvidenceItem]


class AiCareerStrengthsAndInterviewResponse(_CamelModel):
    strengths: list[StrengthItem] = Field(min_length=2, max_length=3)
    interview_questions: list[InterviewQuestion] = Field(min_length=2, max_length=3)
