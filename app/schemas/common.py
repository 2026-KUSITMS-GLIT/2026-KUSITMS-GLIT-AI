"""여러 도메인에서 공유하는 Enum 및 공통 타입."""

from __future__ import annotations

from enum import StrEnum


class JobRole(StrEnum):
    PLANNER = "PLANNER"
    DEVELOPER = "DEVELOPER"
    DESIGNER = "DESIGNER"


class UserStatus(StrEnum):
    STUDENT = "STUDENT"
    JOB_SEEKER = "JOB_SEEKER"
    EMPLOYED = "EMPLOYED"
