"""POST /v1/tagging · POST /api/tagging 통합 테스트.

LLM 호출은 :mod:`respx` 로 Anthropic Messages API 를 모킹한다. LLM 예외 → HTTP 매핑은
``dependency_overrides`` 로 LLMClient 자리에 raise 만 하는 더미를 끼워 검증한다
(LLMClient 의 httpx → 도메인 예외 매핑은 그 자체로 별개 책임이며 tenacity 의 재시도/대기
시간 영향을 받지 않도록 라우터 catch 만 정밀 검증).

PII 안전성: STAR 본문 자리에 ``MAGICPII-*`` 마커를 박아두고, 모든 로그 record 의
``__dict__`` 직렬화에 해당 마커가 없는지 검사한다.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from app.api.v1.tagging import get_llm_client
from app.main import app
from app.services._clients.exceptions import (
    LLMAuthError,
    LLMBadRequestError,
    LLMRateLimitedError,
    LLMUpstreamUnavailableError,
)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

_PAYLOAD: dict[str, Any] = {
    "jobRole": "DEVELOPER",
    "selectedCompetency": "PROBLEM_SOLVING",
    "situationTask": "MAGICPII-ST-1234",
    "action": "MAGICPII-A-5678",
    "result": "MAGICPII-R-9012",
}

_PII_MARKERS = ("MAGICPII-ST-1234", "MAGICPII-A-5678", "MAGICPII-R-9012")


def _anthropic_msg(text: str) -> dict[str, Any]:
    """Anthropic Messages API 응답 형태 (단일 text block)."""
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "test-model",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


def _assert_no_pii_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    """모든 캡처된 record 의 ``__dict__`` 에서 STAR PII 마커가 없는지 검사."""
    for record in caplog.records:
        serialized = repr(record.__dict__)
        for marker in _PII_MARKERS:
            assert marker not in serialized, (
                f"STAR PII marker {marker!r} 가 로그에 노출됨 "
                f"({record.name}.{record.levelname}): {serialized[:200]}"
            )


# === /api/tagging — 안정 경로 더미 ===


def test_api_tagging_dummy_returns_fixed_response(client: TestClient, token: str) -> None:
    r = client.post("/api/tagging", json=_PAYLOAD, headers={"X-Internal-Token": token})
    assert r.status_code == 200
    assert r.json() == {"primaryCategory": "PROBLEM_SOLVING", "detailTags": ["#문제해결"]}


# === /v1/tagging — 인증 ===


def test_v1_tagging_missing_token_returns_401(client: TestClient) -> None:
    r = client.post("/v1/tagging", json=_PAYLOAD)
    assert r.status_code == 401


def test_v1_tagging_wrong_token_returns_403(client: TestClient) -> None:
    r = client.post("/v1/tagging", json=_PAYLOAD, headers={"X-Internal-Token": "wrong"})
    assert r.status_code == 403


# === /v1/tagging — 요청 스키마 검증 (LLM 미호출) ===


@respx.mock
def test_v1_tagging_300char_overflow_returns_422_and_skips_llm(
    client: TestClient, token: str
) -> None:
    # respx 가 anthropic 호출을 mock 하지 않은 상태 — LLM 호출이 일어났다면 unmatched 로 실패.
    bad = {**_PAYLOAD, "action": "a" * 301}
    r = client.post("/v1/tagging", json=bad, headers={"X-Internal-Token": token})
    assert r.status_code == 422


# === /v1/tagging — LLM happy ===


@respx.mock
def test_v1_tagging_happy_path(client: TestClient, token: str) -> None:
    route = respx.post(ANTHROPIC_URL).mock(
        return_value=Response(
            200, json=_anthropic_msg('{"detailTags": ["#원인분석", "#검증및테스트"]}')
        )
    )
    r = client.post("/v1/tagging", json=_PAYLOAD, headers={"X-Internal-Token": token})
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "primaryCategory": "PROBLEM_SOLVING",
        "detailTags": ["#원인분석", "#검증및테스트"],
    }
    assert route.call_count == 1


# === /v1/tagging — corrective 재시도 시나리오 ===


@respx.mock
def test_v1_tagging_corrective_retry_recovers(client: TestClient, token: str) -> None:
    route = respx.post(ANTHROPIC_URL).mock(
        side_effect=[
            Response(200, json=_anthropic_msg('{"detailTags": ["#존재하지않는태그"]}')),
            Response(200, json=_anthropic_msg('{"detailTags": ["#원인분석"]}')),
        ]
    )
    r = client.post("/v1/tagging", json=_PAYLOAD, headers={"X-Internal-Token": token})
    assert r.status_code == 200
    assert r.json()["detailTags"] == ["#원인분석"]
    assert route.call_count == 2


# === /v1/tagging — 두 시도 모두 실패 → 422 TAG_EXTRACTION_FAILED ===


@respx.mock
def test_v1_tagging_double_validation_failure_returns_422(client: TestClient, token: str) -> None:
    route = respx.post(ANTHROPIC_URL).mock(
        side_effect=[
            Response(200, json=_anthropic_msg('{"detailTags": ["#없는태그A"]}')),
            Response(200, json=_anthropic_msg('{"detailTags": ["#없는태그B"]}')),
        ]
    )
    r = client.post("/v1/tagging", json=_PAYLOAD, headers={"X-Internal-Token": token})
    assert r.status_code == 422
    body = r.json()
    assert body["detail"]["code"] == "TAG_EXTRACTION_FAILED"
    assert route.call_count == 2


# === /v1/tagging — 갯수 위반 (0개 / 4개) → corrective 통해 회복 ===


@pytest.mark.parametrize(
    "bad_response",
    [
        '{"detailTags": []}',
        '{"detailTags": ["#원인분석","#검증및테스트","#반복개선","#문제해결"]}',
    ],
    ids=["empty", "four_tags"],
)
@respx.mock
def test_v1_tagging_count_violation_then_recovers_via_corrective(
    client: TestClient, token: str, bad_response: str
) -> None:
    route = respx.post(ANTHROPIC_URL).mock(
        side_effect=[
            Response(200, json=_anthropic_msg(bad_response)),
            Response(200, json=_anthropic_msg('{"detailTags": ["#원인분석"]}')),
        ]
    )
    r = client.post("/v1/tagging", json=_PAYLOAD, headers={"X-Internal-Token": token})
    assert r.status_code == 200
    assert route.call_count == 2


# === /v1/tagging — LLM 예외 → HTTP 매핑 ===


@pytest.mark.parametrize(
    ("exc_cls", "expected_status", "expected_detail"),
    [
        (LLMRateLimitedError, 503, "LLM rate limited"),
        (LLMUpstreamUnavailableError, 502, "LLM upstream unavailable"),
        (LLMBadRequestError, 502, "LLM upstream unavailable"),
        (LLMAuthError, 502, "LLM upstream unavailable"),
    ],
    ids=["rate_limited", "upstream_unavailable", "bad_request", "auth"],
)
def test_v1_tagging_maps_llm_exception_to_http(
    client: TestClient,
    token: str,
    exc_cls: type[Exception],
    expected_status: int,
    expected_detail: str,
) -> None:
    """LLM 도메인 예외 → HTTP 매핑.

    tenacity 재시도/대기 영향 회피를 위해 ``dependency_overrides`` 로 LLMClient 자리에
    바로 raise 하는 더미를 끼운다 (LLMClient 의 httpx → 도메인 예외 매핑은 별도 책임).
    """

    class _RaisingLLM:
        async def create_message(self, **_kwargs: Any) -> Any:
            raise exc_cls("simulated")

    app.dependency_overrides[get_llm_client] = _RaisingLLM
    try:
        r = client.post("/v1/tagging", json=_PAYLOAD, headers={"X-Internal-Token": token})
        assert r.status_code == expected_status
        assert r.json()["detail"] == expected_detail
    finally:
        app.dependency_overrides.clear()


# === /v1/tagging — 로그 PII 안전성 ===


@respx.mock
def test_v1_tagging_does_not_log_star_body_on_happy(
    client: TestClient, token: str, caplog: pytest.LogCaptureFixture
) -> None:
    respx.post(ANTHROPIC_URL).mock(
        return_value=Response(200, json=_anthropic_msg('{"detailTags": ["#원인분석"]}'))
    )
    caplog.set_level(logging.INFO)
    r = client.post("/v1/tagging", json=_PAYLOAD, headers={"X-Internal-Token": token})
    assert r.status_code == 200
    _assert_no_pii_in_logs(caplog)


@respx.mock
def test_v1_tagging_does_not_log_star_body_on_validation_failure(
    client: TestClient, token: str, caplog: pytest.LogCaptureFixture
) -> None:
    respx.post(ANTHROPIC_URL).mock(
        side_effect=[
            Response(200, json=_anthropic_msg('{"detailTags": ["#없는1"]}')),
            Response(200, json=_anthropic_msg('{"detailTags": ["#없는2"]}')),
        ]
    )
    caplog.set_level(logging.INFO)
    r = client.post("/v1/tagging", json=_PAYLOAD, headers={"X-Internal-Token": token})
    assert r.status_code == 422
    _assert_no_pii_in_logs(caplog)
