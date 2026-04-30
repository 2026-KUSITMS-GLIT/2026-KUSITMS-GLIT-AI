"""Spring Boot ↔ AI 서비스 간 내부 토큰 기반 인증."""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Request, status

from app.core.config import get_settings
from app.core.logging import get_logger

_logger = get_logger(__name__)


async def require_internal_token(
    request: Request,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    """FastAPI 의존성 — 요청의 ``X-Internal-Token`` 헤더를 검증한다.

    Spring Boot 백엔드가 모든 요청에 공유 시크릿을 담아 보낸다는 전제로 동작한다.
    새 라우터는 반드시 ``dependencies=[Depends(require_internal_token)]`` 로 보호하며,
    예외 대상은 health 계열(``/healthz``, ``/readyz``) 뿐이다.

    실패 케이스:
        - 헤더 자체가 없을 때 → ``401 Unauthorized``
        - 헤더 값이 일치하지 않을 때 → ``403 Forbidden``

    비교는 :func:`hmac.compare_digest` 로 상수 시간 비교를 수행하여 타이밍 공격을 차단한다.
    실패 시 ``security.denied`` 이벤트를 WARNING 레벨로 남긴다 (JSON 포맷에서
    ``reason`` / ``path`` / ``method`` 가 최상위 필드로 노출된다).

    Raises:
        HTTPException: 헤더 누락(401) 또는 토큰 불일치(403).
    """
    if x_internal_token is None:
        _logger.warning(
            "security.denied",
            extra={
                "reason": "missing_header",
                "path": request.url.path,
                "method": request.method,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="내부 인증 토큰이 없습니다",
        )

    settings = get_settings()
    # bytes 로 인코딩해서 비교 — 헤더 값에 non-ASCII 문자가 섞여도 TypeError(500) 대신
    # 정상적으로 불일치(403)로 떨어지게 한다. timing 안전성은 그대로 유지.
    if not hmac.compare_digest(
        x_internal_token.encode("utf-8"),
        settings.internal_api_token.encode("utf-8"),
    ):
        _logger.warning(
            "security.denied",
            extra={
                "reason": "invalid_token",
                "path": request.url.path,
                "method": request.method,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="내부 인증 토큰이 유효하지 않습니다",
        )
