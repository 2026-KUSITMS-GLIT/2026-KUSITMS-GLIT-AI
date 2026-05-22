"""여러 스키마에서 공유하는 도메인 Enum 과 한글 라벨 매핑.

Spring Boot 백엔드와 동일한 코드값을 유지해야 한다. 새 값이 필요하면 Spring 쪽
ENUM 도 같이 업데이트하고 PR 본문에 그 사실을 남긴다.
"""

from __future__ import annotations

from enum import StrEnum


class JobRole(StrEnum):
    """유저 직군 — Spring 측 enum 코드와 동일."""

    PLANNER = "PLANNER"
    DEVELOPER = "DEVELOPER"
    DESIGNER = "DESIGNER"


class UserStatus(StrEnum):
    """유저 상태 — Spring 측 enum 코드와 동일."""

    STUDENT = "STUDENT"
    JOB_SEEKER = "JOB_SEEKER"
    EMPLOYED = "EMPLOYED"


class PrimaryCategory(StrEnum):
    """5대 직무 역량 — Spring 측 enum 코드와 동일."""

    DISCOVERY_ANALYSIS = "DISCOVERY_ANALYSIS"
    PLANNING_EXECUTION = "PLANNING_EXECUTION"
    COLLABORATION = "COLLABORATION"
    PROBLEM_SOLVING = "PROBLEM_SOLVING"
    REFLECTION_GROWTH = "REFLECTION_GROWTH"


JOB_ROLE_LABELS_KO: dict[JobRole, str] = {
    JobRole.PLANNER: "기획",
    JobRole.DEVELOPER: "개발",
    JobRole.DESIGNER: "디자인",
}
"""프롬프트 변수 치환 등에서 쓰는 한글 라벨. tags.txt 가중치 표 헤더와 동일."""


PRIMARY_CATEGORY_LABELS_KO: dict[PrimaryCategory, str] = {
    PrimaryCategory.DISCOVERY_ANALYSIS: "발견·분석",
    PrimaryCategory.PLANNING_EXECUTION: "기획·실행",
    PrimaryCategory.COLLABORATION: "협업·조율",
    PrimaryCategory.PROBLEM_SOLVING: "문제해결·개선",
    PrimaryCategory.REFLECTION_GROWTH: "성찰·성장",
}
"""프롬프트 변수 치환에서 쓰는 한글 라벨. tags.txt 카테고리 표기와 동일."""
