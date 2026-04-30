"""ALB / ECS 헬스체크용 liveness · readiness 엔드포인트.

이 라우터는 **내부 토큰 인증의 예외 대상** 이다. Spring Boot 가 아니라 ALB/ECS 에이전트가
직접 호출하기 때문에 ``X-Internal-Token`` 헤더 없이도 200 을 돌려줘야 한다.
(v1 라우터에 전역 토큰 보호가 걸리므로 이 라우터는 ``/v1`` prefix 밖에 둔다.)
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import __version__

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    """프로세스 생존 여부 응답."""

    status: str = Field(description="항상 'ok'. 컨테이너가 살아있음을 의미한다.")
    version: str = Field(description="현재 배포된 앱 버전 (``app.__version__``).")


class CheckResult(BaseModel):
    """개별 의존성 체크 결과. ``/readyz`` 의 ``checks`` 항목으로 쌓인다."""

    name: str = Field(description="체크 대상 이름 (예: ``anthropic``, ``redis``).")
    ok: bool = Field(description="정상 여부.")
    detail: str | None = Field(default=None, description="실패/경고 시 짧은 사유.")


class ReadinessResponse(BaseModel):
    """트래픽 수신 준비 상태 응답.

    현재는 프로세스 부팅 여부만 반영한다. 외부 의존성(AI provider 등) 체크를 추가할 때는
    :class:`CheckResult` 를 만들어 ``checks`` 에 append 하고, 하나라도 ``ok=False`` 면
    ``status='degraded'`` 로 내려준다.
    """

    status: str = Field(description="``ready`` / ``degraded`` 중 하나.")
    checks: list[CheckResult] = Field(
        default_factory=list,
        description="개별 외부 의존성 체크 결과. 현재는 비어 있음 (확장 포인트).",
    )


@router.get(
    "/healthz",
    summary="Liveness probe",
    description="ALB/ECS liveness 체크용. 프로세스가 살아있으면 200 을 반환한다.",
    response_model=LivenessResponse,
)
async def healthz() -> LivenessResponse:
    """프로세스 생존 신호.

    절대 외부 호출을 태우지 않는다. 외부 의존성이 죽었을 때 liveness 가 실패하면
    ECS 가 컨테이너를 재시작해버리는데, 그래봤자 외부가 살아날 리 없으므로 문제만 커진다.
    """
    return LivenessResponse(status="ok", version=__version__)


@router.get(
    "/readyz",
    summary="Readiness probe",
    description="트래픽 수신 준비 여부. 배포 파이프라인이 이 엔드포인트 200 을 기다린다.",
    response_model=ReadinessResponse,
)
async def readyz() -> ReadinessResponse:
    """트래픽 수신 준비 신호.

    저렴하게 유지한다. 외부 AI provider 의 일시 장애로 readiness 가 flap 하면
    롤링 배포가 불필요하게 실패하므로, 외부 호출은 여기서 하지 않는다.
    DB 연결 등 **앱 내부에서 끊길 수 있는** 의존성만 :class:`CheckResult` 로 넣는다.
    """
    checks: list[CheckResult] = []
    status = "ready" if all(c.ok for c in checks) else "degraded"
    return ReadinessResponse(status=status, checks=checks)
