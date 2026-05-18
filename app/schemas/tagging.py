"""``POST /v1/tagging`` · ``POST /api/tagging`` 요청·응답 스키마.

api_spec 계약대로 본문은 camelCase 로 주고받고, 내부 파이썬 코드는 snake_case 로 다룬다.
``populate_by_name=True`` 로 두 이름 모두 받을 수 있게 하고, FastAPI 응답 직렬화는
라우터에서 ``response_model_by_alias=True`` 로 camelCase 출력을 강제한다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import JobRole, PrimaryCategory

_MAX_STAR_LENGTH = 300
"""S·T / A / R 각 단계 본문의 최대 길이 (api_spec 명시)."""


class TaggingRequest(BaseModel):
    """심화 STAR 기록 1건에 대한 태깅 요청.

    Spring 이 1차 검증한 값이 넘어온다는 전제이지만, AI 서비스도 동일한 가드를 둔다.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    job_role: JobRole = Field(alias="jobRole", description="유저 직군")
    selected_competency: PrimaryCategory = Field(
        alias="selectedCompetency",
        description="유저가 확정한 5대 직무 역량",
    )
    situation_task: str = Field(
        alias="situationTask",
        min_length=1,
        max_length=_MAX_STAR_LENGTH,
        description="S·T 단계 본문",
    )
    action: str = Field(
        min_length=1,
        max_length=_MAX_STAR_LENGTH,
        description="A 단계 본문",
    )
    result: str = Field(
        min_length=1,
        max_length=_MAX_STAR_LENGTH,
        description="R 단계 본문",
    )


class TaggingResponse(BaseModel):
    """태깅 응답.

    ``primaryCategory`` 는 요청의 ``selectedCompetency`` 그대로 echo (api_spec 계약).
    ``detailTags`` 는 65개 태그풀 안에서 1~3개를 한글 raw 문자열로 반환하며, Spring 측에서
    한글 → 내부 ENUM 코드로 매핑한다.
    """

    model_config = ConfigDict(populate_by_name=True)

    primary_category: PrimaryCategory = Field(alias="primaryCategory")
    detail_tags: list[str] = Field(
        alias="detailTags",
        min_length=1,
        max_length=3,
        description="65개 태그풀에서 추출한 세부 태그 (한글 raw)",
    )
