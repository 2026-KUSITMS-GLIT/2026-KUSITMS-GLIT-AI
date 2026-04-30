"""``/healthz`` · ``/readyz`` — 인증 예외, 응답 스키마."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestHealthz:
    def test_returns_200_without_token(self, client: TestClient) -> None:
        r = client.get("/healthz")
        assert r.status_code == 200

    def test_response_shape(self, client: TestClient) -> None:
        body = client.get("/healthz").json()
        assert body["status"] == "ok"
        assert isinstance(body["version"], str)


class TestReadyz:
    def test_returns_200_without_token(self, client: TestClient) -> None:
        r = client.get("/readyz")
        assert r.status_code == 200

    def test_response_shape(self, client: TestClient) -> None:
        body = client.get("/readyz").json()
        assert body["status"] == "ready"
        assert body["checks"] == []
