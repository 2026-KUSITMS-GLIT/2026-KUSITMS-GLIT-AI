"""POST /api/tagging — Spring 이 호출할 안정 경로 (현재 더미 응답).

이 라우터는 백엔드와 합의된 최종 endpoint 의 자리를 미리 잡아두기 위한 것이다.
``/v1/tagging`` 의 v1_baseline 이 검증을 마치면 **이 핸들러 본문만** service 호출로
교체하는 cutover 가 일어난다. 그동안 Spring 측은 이 경로로 연동을 진행할 수 있다
(요청·응답 스키마는 동일, 응답 내용만 고정 더미).

라우터 책임:
    - 요청 스키마 검증 (FastAPI 가 ``TaggingRequest`` 로 처리)
    - ``X-Internal-Token`` 인증 (라우터 전역 dependency)
    - 고정 더미 응답 반환 (LLM 호출 없음)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import require_internal_token
from app.schemas.tagging import TaggingRequest, TaggingResponse

router = APIRouter(
    prefix="/api",
    tags=["tagging-public"],
    dependencies=[Depends(require_internal_token)],
)


@router.post(
    "/tagging",
    summary="STAR 심화 기록 세부 역량 태그 추출 (안정 경로 · 현재 더미)",
    description=(
        "Spring 이 호출하기로 합의한 최종 경로. 현재는 요청 스키마 검증만 통과시키고 "
        "고정 더미 JSON 을 돌려준다. v1_baseline 검증 후 cutover 시 이 핸들러 본문을 "
        "``service.tagging.run()`` 호출로 교체한다."
    ),
    response_model=TaggingResponse,
    response_model_by_alias=True,
)
async def tagging_public(req: TaggingRequest) -> TaggingResponse:
    # TODO(cutover): 이 본문을 app/api/v1/tagging.py 의 tagging_v1 과 동일한 흐름
    #   (LLMClient dependency 주입 → service.tagging.run() 호출 → LLM/검증 예외 →
    #    HTTP 매핑) 으로 교체. v1 라우터의 패턴을 그대로 복붙하면 된다.
    return TaggingResponse(
        primary_category=req.selected_competency,
        detail_tags=["#문제해결"],
    )
