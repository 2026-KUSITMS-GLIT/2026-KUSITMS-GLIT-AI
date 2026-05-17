"""Request-scoped context variables.

요청마다 고유한 request_id를 발급하고,
해당 요청을 처리하는 동안 어디서든 꺼내 쓸 수 있도록 contextvars로 관리한다.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

# 현재 요청의 request_id. 미들웨어에서 set, 로거에서 get.
_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(value: str | None = None) -> str:
    """request_id를 설정한다. value가 없으면 uuid4로 새로 생성."""
    rid = value or uuid.uuid4().hex
    _request_id.set(rid)
    return rid


def get_request_id() -> str:
    """현재 요청의 request_id를 반환한다."""
    return _request_id.get()
