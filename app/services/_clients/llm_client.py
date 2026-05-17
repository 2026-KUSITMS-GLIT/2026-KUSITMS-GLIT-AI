"""LLMClient — Anthropic SDK 랩퍼.

services/ 이하 코드는 Anthropic SDK 를 직접 사용하지 않고 이 클래스만 쓴다.
타임아웃, 재시도, 에러 변환을 한 곳에서 관리한다.

Workload:
    TAGGING — 짧은 호출. read timeout 15s, 최대 3회 시도.
    REPORT  — 긴 호출. read timeout 90s, 최대 2회 시도.
"""

from __future__ import annotations

import asyncio
import time
from enum import StrEnum
from typing import Any

import anthropic
import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from app.core.logging import get_logger
from app.services._clients.exceptions import (
    LLMAuthError,
    LLMBadRequestError,
    LLMRateLimitedError,
    LLMUpstreamUnavailableError,
)

logger = get_logger(__name__)


class WorkloadType(StrEnum):
    TAGGING = "tagging"
    REPORT = "report"


# 워크로드별 timeout 프로파일 (httpx.Timeout 인자와 동일)
_TIMEOUT_PROFILES: dict[WorkloadType, httpx.Timeout] = {
    WorkloadType.TAGGING: httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0),
    WorkloadType.REPORT: httpx.Timeout(connect=5.0, read=90.0, write=10.0, pool=5.0),
}

# 워크로드별 동시 호출 제한
_SEMAPHORES: dict[WorkloadType, asyncio.Semaphore] = {
    WorkloadType.TAGGING: asyncio.Semaphore(8),
    WorkloadType.REPORT: asyncio.Semaphore(4),
}


def _is_retryable(exc: BaseException) -> bool:
    """재시도할 수 있는 예외인지 판단한다."""
    if isinstance(exc, anthropic.RateLimitError):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code in {408, 409, 500, 502, 503, 504, 529}
    return isinstance(exc, (anthropic.APIConnectionError, httpx.TimeoutException))


def _map_exception(
    exc: Exception,
) -> LLMUpstreamUnavailableError | LLMRateLimitedError | LLMBadRequestError | LLMAuthError:
    """Anthropic SDK 예외를 도메인 예외로 변환한다."""
    if isinstance(exc, anthropic.RateLimitError):
        return LLMRateLimitedError(str(exc))
    if isinstance(exc, anthropic.AuthenticationError):
        logger.error("llm.auth_failed", extra={"error": str(exc)})
        return LLMAuthError(str(exc))
    if isinstance(exc, anthropic.PermissionDeniedError):
        logger.error("llm.auth_failed", extra={"error": str(exc)})
        return LLMAuthError(str(exc))
    if isinstance(exc, anthropic.BadRequestError):
        return LLMBadRequestError(str(exc))
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code in {400, 422}:
        return LLMBadRequestError(str(exc))
    return LLMUpstreamUnavailableError(str(exc))


class LLMClient:
    """Anthropic Claude API 호출용 싱글턴 클라이언트.

    lifespan 에서 1회 생성하여 app.state 에 보관한다.
    """

    def __init__(self, api_key: str) -> None:
        # SDK 내장 재시도는 끄고 (tenacity 로 일원화)
        self._client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=0)

    async def aclose(self) -> None:
        await self._client.close()

    async def create_message(
        self,
        *,
        workload: WorkloadType,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int = 1000,
    ) -> anthropic.types.Message:
        """Claude API 를 호출한다.

        Args:
            workload: TAGGING 또는 REPORT. timeout 및 재시도 회수가 달라진다.
            model: 사용할 Claude 모델명. (Settings 에서 주입)
            messages: 호출 메시지 리스트.
            system: 시스템 프롬프트.
            max_tokens: 최대 출력 토큰 수.

        Returns:
            Anthropic Message 객체.

        Raises:
            LLMUpstreamUnavailable: 5xx, 타임아웃 등.
            LLMRateLimited: 429 재시도 후에도 실패.
            LLMBadRequest: 4xx 페이로드 문제.
            LLMAuthError: API 키 문제.
        """
        max_attempts = 3 if workload == WorkloadType.TAGGING else 2
        multiplier = 0.5 if workload == WorkloadType.TAGGING else 1.0
        max_wait = 8 if workload == WorkloadType.TAGGING else 20
        timeout = _TIMEOUT_PROFILES[workload]
        semaphore = _SEMAPHORES[workload]

        @retry(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(max_attempts),
            wait=wait_random_exponential(multiplier=multiplier, max=max_wait),
            reraise=True,
        )
        async def _call() -> anthropic.types.Message:
            async with semaphore:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "timeout": timeout,
                }
                if system:
                    kwargs["system"] = system
                result = await self._client.messages.create(**kwargs)
                assert isinstance(result, anthropic.types.Message)
                return result

        start = time.perf_counter()
        attempt = 0
        try:
            attempt += 1
            response = await _call()
            latency_ms = round((time.perf_counter() - start) * 1000)
            logger.info(
                "llm.done",
                extra={
                    "workload": workload,
                    "model": model,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "latency_ms": latency_ms,
                    "stop_reason": response.stop_reason,
                },
            )
            return response
        except Exception as exc:
            raise _map_exception(exc) from exc
