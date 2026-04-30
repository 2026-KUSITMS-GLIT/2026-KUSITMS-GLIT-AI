"""스캐폴드 카나리 — ``/v1/_ping``.

v1 라우터 전역에 ``X-Internal-Token`` 보호가 잘 걸려 있는지 실제 요청으로 확인하기 위한
**임시** 엔드포인트. 첫 실제 feature 라우터가 붙으면 지워도 된다 (그때는 그 feature 가
같은 보호를 받는 것으로 검증되므로).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["_internal"])


@router.get(
    "/_ping",
    summary="스캐폴드 카나리 — 인증/라우팅 확인용",
    description=(
        "내부 토큰 보호가 v1 라우터 전역에 잘 적용됐는지 확인하는 임시 엔드포인트. "
        "첫 실제 feature 가 붙으면 제거해도 된다."
    ),
)
async def ping() -> dict[str, str]:
    return {"pong": "ok"}
