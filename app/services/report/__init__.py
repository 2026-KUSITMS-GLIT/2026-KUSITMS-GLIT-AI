"""report_variant 환경변수로 활성 구현체를 선택해 export한다."""

from __future__ import annotations

import importlib
from functools import lru_cache
from types import ModuleType

from app.core.config import get_settings
from app.schemas.report import (
    AiCareerBrandingResponse,
    AiCareerHighlightsResponse,
    AiCareerNarrativeResponse,
    AiCareerStrengthsAndInterviewResponse,
    AiMiniReportResponse,
    AiReportRequest,
)
from app.services._clients.llm_client import LLMClient

_VARIANTS = {"v1_baseline"}


@lru_cache(maxsize=1)
def _get_impl() -> ModuleType:
    variant = get_settings().report_variant
    if variant not in _VARIANTS:
        raise RuntimeError(
            f"REPORT_VARIANT='{variant}' 는 유효하지 않습니다. 사용 가능한 값: {sorted(_VARIANTS)}"
        )
    return importlib.import_module(f"app.services.report.{variant}")


async def run_mini(req: AiReportRequest, llm: LLMClient, model: str) -> AiMiniReportResponse:
    return await _get_impl().run_mini(req, llm, model)  # type: ignore[no-any-return]


async def run_branding(
    req: AiReportRequest, llm: LLMClient, model: str
) -> AiCareerBrandingResponse:
    return await _get_impl().run_branding(req, llm, model)  # type: ignore[no-any-return]


async def run_narrative(
    req: AiReportRequest, llm: LLMClient, model: str
) -> AiCareerNarrativeResponse:
    return await _get_impl().run_narrative(req, llm, model)  # type: ignore[no-any-return]


async def run_strengths_and_interview(
    req: AiReportRequest, llm: LLMClient, model: str
) -> AiCareerStrengthsAndInterviewResponse:
    return await _get_impl().run_strengths_and_interview(req, llm, model)  # type: ignore[no-any-return]


async def run_highlights(
    req: AiReportRequest, llm: LLMClient, model: str
) -> AiCareerHighlightsResponse:
    return await _get_impl().run_highlights(req, llm, model)  # type: ignore[no-any-return]
