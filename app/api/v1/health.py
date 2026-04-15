"""Liveness / readiness endpoints for ALB + ECS health checks."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/readyz", summary="Readiness probe")
async def readyz() -> dict[str, str]:
    # Keep cheap — just confirms the process is up. Downstream (외부 AI provider 등)
    # reachability는 여기서 체크하지 않는다. transient outage로 readiness가 flap하는 걸 피하기 위함.
    return {"status": "ready"}
