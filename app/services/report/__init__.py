"""report_variant 환경변수로 활성 구현체를 선택해 export한다."""

from __future__ import annotations

import importlib

from app.core.config import get_settings
from app.schemas.report import (
    AiCareerBrandingResponse,
    AiCareerHighlightsResponse,
    AiCareerInterviewRequest,
    AiCareerInterviewResponse,
    AiCareerNarrativeResponse,
    AiCareerStrengthsResponse,
    AiMiniReportResponse,
    AiReportRequest,
)

_VARIANTS = {"v1_baseline"}

_variant = get_settings().report_variant

if _variant not in _VARIANTS:
    raise RuntimeError(
        f"REPORT_VARIANT='{_variant}' 는 유효하지 않습니다. 사용 가능한 값: {sorted(_VARIANTS)}"
    )

_impl = importlib.import_module(f"app.services.report.{_variant}")


async def run_mini(req: AiReportRequest) -> AiMiniReportResponse:
    return await _impl.run_mini(req)  # type: ignore[no-any-return]


async def run_branding(req: AiReportRequest) -> AiCareerBrandingResponse:
    return await _impl.run_branding(req)  # type: ignore[no-any-return]


async def run_narrative(req: AiReportRequest) -> AiCareerNarrativeResponse:
    return await _impl.run_narrative(req)  # type: ignore[no-any-return]


async def run_strengths(req: AiReportRequest) -> AiCareerStrengthsResponse:
    return await _impl.run_strengths(req)  # type: ignore[no-any-return]


async def run_highlights(req: AiReportRequest) -> AiCareerHighlightsResponse:
    return await _impl.run_highlights(req)  # type: ignore[no-any-return]


async def run_interview(req: AiCareerInterviewRequest) -> AiCareerInterviewResponse:
    return await _impl.run_interview(req)  # type: ignore[no-any-return]
