"""``require_internal_token`` 의존성 — 헤더 검증, non-ASCII 안전성, v1 라우터 연결."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.security import require_internal_token


@pytest.fixture
def fake_request() -> MagicMock:
    """로그에서 ``path`` / ``method`` 만 참조하는 최소 Request 스텁."""
    req = MagicMock()
    req.url.path = "/v1/_ping"
    req.method = "GET"
    return req


class TestDirectCall:
    """의존성 함수를 직접 호출해 unit 레벨에서 검증."""

    async def test_missing_header_raises_401(self, fake_request: MagicMock) -> None:
        with pytest.raises(HTTPException) as exc:
            await require_internal_token(fake_request, x_internal_token=None)
        assert exc.value.status_code == 401
        assert "없습니다" in exc.value.detail

    async def test_wrong_token_raises_403(self, fake_request: MagicMock) -> None:
        with pytest.raises(HTTPException) as exc:
            await require_internal_token(fake_request, x_internal_token="wrong")
        assert exc.value.status_code == 403
        assert "유효하지 않습니다" in exc.value.detail

    async def test_correct_token_does_not_raise(self, fake_request: MagicMock, token: str) -> None:
        # require_internal_token 은 성공 시 아무것도 반환하지 않으므로 raise 없음이 통과.
        await require_internal_token(fake_request, x_internal_token=token)

    async def test_non_ascii_token_returns_403(self, fake_request: MagicMock) -> None:
        """한글/이모지 등 non-ASCII 토큰도 ``TypeError`` 없이 403 으로 떨어진다.

        ``hmac.compare_digest`` 를 bytes 로 호출하도록 바뀐 픽스 이후의 회귀 방지 테스트.
        (HTTP 레벨로는 httpx 가 헤더를 ASCII 강제라 직접 호출로만 재현 가능.)
        """
        with pytest.raises(HTTPException) as exc:
            await require_internal_token(fake_request, x_internal_token="한글토큰🤖")
        assert exc.value.status_code == 403


class TestV1Integration:
    """v1 aggregator 에 보호가 실제로 걸리는지 HTTP 레벨에서 검증."""

    def test_no_token_returns_401(self, client: TestClient) -> None:
        r = client.get("/v1/_ping")
        assert r.status_code == 401

    def test_wrong_token_returns_403(self, client: TestClient) -> None:
        r = client.get("/v1/_ping", headers={"X-Internal-Token": "wrong"})
        assert r.status_code == 403

    def test_correct_token_returns_200(self, client: TestClient, token: str) -> None:
        r = client.get("/v1/_ping", headers={"X-Internal-Token": token})
        assert r.status_code == 200
        assert r.json() == {"pong": "ok"}
