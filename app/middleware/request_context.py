"""RequestContextMiddleware — request_id 발급 및 액세스 로그.

모든 요청에 대해:
1. X-Request-ID 헤더가 있으면 그 값을, 없으면 uuid4 로 request_id 를 발급한다.
2. request_id 를 contextvars 에 저장해 이후 모든 로그에 자동으로 포함되게 한다.
3. 응답 헤더에 X-Request-ID 를 echo 한다.
4. 요청 완료 후 elapsed_ms 를 포함한 액세스 로그 한 줄을 남긴다.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import get_request_id, set_request_id
from app.core.logging import get_logger

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """request_id 전파 + 액세스 로그 미들웨어."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 1. request_id 발급 (Spring Boot 가 X-Request-ID 를 보내면 그 값 재사용)
        incoming = request.headers.get("X-Request-ID")
        rid = set_request_id(incoming)

        # 2. 요청 처리
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000)

        # 3. 응답 헤더에 request_id echo
        response.headers["X-Request-ID"] = rid
        response.headers["X-Elapsed-Ms"] = str(elapsed_ms)

        # 4. 액세스 로그
        logger.info(
            "request.done",
            extra={
                "request_id": get_request_id(),
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "elapsed_ms": elapsed_ms,
            },
        )

        return response
