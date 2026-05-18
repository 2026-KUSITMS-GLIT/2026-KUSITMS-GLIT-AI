"""Tagging 도메인 entry — 활성 variant 의 ``run`` 함수를 dispatch.

``Settings.tagging_variant`` (env: ``TAGGING_VARIANT``) 값으로 어느 구현체를 쓸지 정한다.
모듈 import 시점에 ``get_settings()`` 를 호출하지 않고 (테스트/lifespan 부팅 순서에 영향 X),
``run()`` 첫 호출 시 lazy resolve 한 뒤 :func:`functools.lru_cache` 로 결과를 캐시한다.

새 variant 를 추가할 때:
    1. ``app/prompts/tagging/{variant}.md`` 작성
    2. ``app/services/tagging/{variant}.py`` 에 동일 시그니처의 ``run`` 작성
    3. :func:`_resolve` 의 분기에 한 줄 추가
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import lru_cache

from app.core.config import get_settings
from app.schemas.tagging import TaggingRequest, TaggingResponse
from app.services._clients.llm_client import LLMClient

RunFn = Callable[[TaggingRequest, LLMClient, str], Awaitable[TaggingResponse]]


@lru_cache(maxsize=1)
def _resolve() -> RunFn:
    """``Settings.tagging_variant`` 에 맞는 ``run`` 함수를 import 해 반환한다."""
    variant = get_settings().tagging_variant
    if variant == "v1_baseline":
        from app.services.tagging.v1_baseline import run as _impl  # noqa: PLC0415

        return _impl
    if variant == "v2_postscore":
        from app.services.tagging.v2_postscore import run as _impl  # noqa: PLC0415

        return _impl
    raise RuntimeError(
        f"Unknown TAGGING_VARIANT={variant!r}. "
        "Add a branch in app/services/tagging/__init__.py::_resolve."
    )


async def run(req: TaggingRequest, llm: LLMClient, model: str) -> TaggingResponse:
    """활성 variant 의 ``run`` 으로 dispatch."""
    return await _resolve()(req, llm, model)


__all__ = ["run"]
