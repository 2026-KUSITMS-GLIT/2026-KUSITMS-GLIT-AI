"""v1 라우터 aggregator.

모든 v1 엔드포인트는 이 라우터에 붙고, 전역적으로 ``X-Internal-Token`` 검증을 거친다.
새 기능은 ``app/api/v1/<feature>.py`` 를 만들어 ``APIRouter`` 하나를 export 한 뒤
아래 ``include_router`` 목록에 한 줄 추가하면 된다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1 import ping
from app.core.security import require_internal_token

router = APIRouter(
    prefix="/v1",
    dependencies=[Depends(require_internal_token)],
)

# Feature 라우터 등록 — 새 기능은 한 줄씩 여기에 추가.
router.include_router(ping.router)
