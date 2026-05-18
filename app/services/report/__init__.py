"""report_variant 환경변수로 활성 구현체를 선택해 export한다."""

from __future__ import annotations

from app.core.config import get_settings
from app.services.report import v1_baseline

_VARIANTS = {
    "v1_baseline": v1_baseline,
}

_settings = get_settings()
_variant = _settings.report_variant

if _variant not in _VARIANTS:
    raise RuntimeError(
        f"REPORT_VARIANT='{_variant}' 는 유효하지 않습니다. 사용 가능한 값: {list(_VARIANTS)}"
    )

_impl = _VARIANTS[_variant]

run_mini = _impl.run_mini
run_branding = _impl.run_branding
run_narrative = _impl.run_narrative
run_strengths = _impl.run_strengths
run_highlights = _impl.run_highlights
run_interview = _impl.run_interview
