"""LLM 호출 실패 시 사용하는 도메인 예외 계층.

Anthropic SDK 예외는 LLMClient 안에서만 노출되고,
services/ 이하 코드는 이 예외만 안다.
"""

from __future__ import annotations


class LLMError(Exception):
    """LLM 호출 실패 베이스 예외."""


class LLMUpstreamUnavailable(LLMError):
    """5xx, 커넥션 에러, 타임아웃 등 일시적 장애."""


class LLMRateLimited(LLMError):
    """429 요청 쿼타 초과. 재시도 후에도 실패."""


class LLMBadRequest(LLMError):
    """400 / 422 우리가 보낸 페이로드 문제."""


class LLMAuthError(LLMError):
    """401 / 403 API 키 문제. 외부에는 upstream unavailable 로 노출."""
