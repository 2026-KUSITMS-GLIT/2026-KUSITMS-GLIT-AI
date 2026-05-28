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
from app.schemas.common import JobRole
from app.services._clients.exceptions import (
    LLMAuthError,
    LLMBadRequestError,
    LLMRateLimitedError,
    LLMUpstreamUnavailableError,
)
from app.services.tagging.exceptions import TaggingValidationError
from app.services.tagging.v2_postscore import (
    _extract_json_payload as _v2_extract_json_payload,
)
from app.services.tagging.v2_postscore import (
    _parse_and_validate as _v2_parse_and_validate,
)
from app.services.tagging.v2_postscore import (
    _select_top3 as _v2_select_top3,
)
from app.services.tagging.v2_postscore import (
    _strip_code_fence as _v2_strip_code_fence,
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

# v2_postscore happy LLM 응답 — assistant prefill('{') 적용 가정 (issue #18).
# 코드가 prefill + raw 로 합쳐 `{"detailTags": [...]}` JSON 을 완성한다.
# 5개 후보 모두 풀 내·중복 없음. DEVELOPER 가중치로 5개 모두 High(3) 동점 →
# tie-break 입력 순서 top3 = ["#원인분석","#검증및테스트","#반복개선"].
_HAPPY_LLM_RAW = '"detailTags": ["#원인분석","#검증및테스트","#반복개선","#문제해결","#디버깅"]}'
_HAPPY_TOP3 = ["#원인분석", "#검증및테스트", "#반복개선"]


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
        return_value=Response(200, json=_anthropic_msg(_HAPPY_LLM_RAW))
    )
    r = client.post("/v1/tagging", json=_PAYLOAD, headers={"X-Internal-Token": token})
    assert r.status_code == 200
    assert r.json() == {"primaryCategory": "PROBLEM_SOLVING", "detailTags": _HAPPY_TOP3}
    assert route.call_count == 1


# === /v1/tagging — corrective 재시도 시나리오 ===


@respx.mock
def test_v1_tagging_corrective_retry_recovers(client: TestClient, token: str) -> None:
    # 1차: 풀-외 + 갯수 미달 → 검증 실패. 2차: 풀 내 5개 → top3 자르고 응답.
    # mock 응답은 모두 assistant prefill('{') 가정 (issue #18).
    route = respx.post(ANTHROPIC_URL).mock(
        side_effect=[
            Response(200, json=_anthropic_msg('"detailTags": ["#존재하지않는태그"]}')),
            Response(200, json=_anthropic_msg(_HAPPY_LLM_RAW)),
        ]
    )
    r = client.post("/v1/tagging", json=_PAYLOAD, headers={"X-Internal-Token": token})
    assert r.status_code == 200
    assert r.json()["detailTags"] == _HAPPY_TOP3
    assert route.call_count == 2


# === /v1/tagging — 두 시도 모두 실패 → 422 TAG_EXTRACTION_FAILED ===


@respx.mock
def test_v1_tagging_double_validation_failure_returns_422(client: TestClient, token: str) -> None:
    route = respx.post(ANTHROPIC_URL).mock(
        side_effect=[
            Response(200, json=_anthropic_msg('"detailTags": ["#없는태그A"]}')),
            Response(200, json=_anthropic_msg('"detailTags": ["#없는태그B"]}')),
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
        '"detailTags": []}',
        '"detailTags": ["#원인분석","#검증및테스트","#반복개선","#문제해결"]}',
        '"detailTags": ["#A","#B","#C","#D","#E","#F","#G","#H"]}',
    ],
    ids=["empty_under_min", "four_tags_under_min", "eight_tags_over_max"],
)
@respx.mock
def test_v1_tagging_count_violation_then_recovers_via_corrective(
    client: TestClient, token: str, bad_response: str
) -> None:
    route = respx.post(ANTHROPIC_URL).mock(
        side_effect=[
            Response(200, json=_anthropic_msg(bad_response)),
            Response(200, json=_anthropic_msg(_HAPPY_LLM_RAW)),
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
    respx.post(ANTHROPIC_URL).mock(return_value=Response(200, json=_anthropic_msg(_HAPPY_LLM_RAW)))
    caplog.set_level(logging.INFO)
    r = client.post("/v1/tagging", json=_PAYLOAD, headers={"X-Internal-Token": token})
    assert r.status_code == 200
    _assert_no_pii_in_logs(caplog)


# === v2_postscore — unit tests ===


@pytest.mark.parametrize(
    "wrapped",
    [
        '{"detailTags": ["#문제해결"]}',
        '`{"detailTags": ["#문제해결"]}`',
        '``{"detailTags": ["#문제해결"]}``',
        '```\n{"detailTags": ["#문제해결"]}\n```',
        '```json\n{"detailTags": ["#문제해결"]}\n```',
    ],
    ids=["no_fence", "single_backtick", "double_backtick", "triple_backtick", "triple_json"],
)
def test_v2_postscore_strips_all_backtick_widths(wrapped: str) -> None:
    """v2 의 정규식이 1·2·3개 백틱 + 옵션 ``json`` prefix 모두 strip 하는지 검증."""
    assert _v2_strip_code_fence(wrapped) == '{"detailTags": ["#문제해결"]}'


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"detailTags": ["#문제해결"]}', '{"detailTags": ["#문제해결"]}'),
        ('다음과 같습니다: {"detailTags": ["#문제해결"]}', '{"detailTags": ["#문제해결"]}'),
        (
            '# 결과\n{"detailTags": ["#문제해결"]}\n참고: ...',
            '{"detailTags": ["#문제해결"]}',
        ),
        ('  \n{"detailTags": ["#문제해결"]}  ', '{"detailTags": ["#문제해결"]}'),
        (
            '```json\n{"detailTags": ["#문제해결"]}\n```',
            '{"detailTags": ["#문제해결"]}',
        ),
        ("브레이스없음", "브레이스없음"),
    ],
    ids=[
        "clean",
        "korean_prefix",
        "markdown_prefix_and_suffix",
        "whitespace",
        "code_fence",
        "no_braces_passthrough",
    ],
)
def test_v2_postscore_extracts_json_payload_from_messy_responses(raw: str, expected: str) -> None:
    """도입어 / 헤딩 / 공백 / 코드펜스 prefix·suffix 를 흡수해 JSON object 본문만 슬라이스.

    issue #18 — Haiku 가 ``다음과 같습니다:`` 같은 도입어를 자주 붙여 ``^{`` 만 허용하면
    운영 실패율이 과도하게 높아짐. ``{`` ~ ``}`` 슬라이스 fallback 으로 흡수.
    """
    assert _v2_extract_json_payload(raw) == expected


def test_v2_postscore_parse_and_validate_handles_intro_prefix() -> None:
    """도입어가 붙은 응답도 정상 파싱 — _extract_json_payload 가 prefix 흡수."""
    raw = (
        "다음과 같습니다: "
        '{"detailTags": ["#원인분석","#검증및테스트","#반복개선","#문제해결","#디버깅"]}'
    )
    tags = _v2_parse_and_validate(raw)
    assert tags == ["#원인분석", "#검증및테스트", "#반복개선", "#문제해결", "#디버깅"]


def test_v2_postscore_parse_accepts_5_to_7_candidates() -> None:
    """후보 갯수 5~7 범위는 통과."""
    five = '{"detailTags": ["#원인분석","#검증및테스트","#반복개선","#문제해결","#디버깅"]}'
    seven = (
        '{"detailTags": '
        '["#원인분석","#검증및테스트","#반복개선","#문제해결","#디버깅","#가설검증","#성능최적화"]}'
    )
    assert len(_v2_parse_and_validate(five)) == 5
    assert len(_v2_parse_and_validate(seven)) == 7


@pytest.mark.parametrize(
    "raw",
    [
        '{"detailTags": ["#원인분석","#검증및테스트","#반복개선","#문제해결"]}',
        ('{"detailTags": ["#A","#B","#C","#D","#E","#F","#G","#H"]}'),
    ],
    ids=["four_tags_under_min", "eight_tags_over_max"],
)
def test_v2_postscore_parse_rejects_out_of_range_candidate_count(raw: str) -> None:
    """후보 갯수가 [5, 7] 범위 밖이면 TaggingValidationError."""
    with pytest.raises(TaggingValidationError, match="후보 갯수 위반"):
        _v2_parse_and_validate(raw)


def test_v2_postscore_select_top3_sorts_by_weight_then_input_order() -> None:
    """가중치 점수 내림차순, 동점은 입력 인덱스 작은 게 먼저."""
    # 개발자(DEVELOPER) 기준 점수:
    #   #기술리서치=High(3) · #UX설계=Low(1) · #API연동=High(3) · #디버깅=High(3)
    #   · #비주얼디자인=Low(1) · #피드백수용=High(3)
    # 입력 순서: 기술리서치 / UX설계 / API연동 / 디버깅 / 비주얼디자인 / 피드백수용
    # 점수 동점(3) 셋 — 입력 순서로 기술리서치 / API연동 / 디버깅 이 top 3.
    candidates = ["#기술리서치", "#UX설계", "#API연동", "#디버깅", "#비주얼디자인", "#피드백수용"]
    top = _v2_select_top3(candidates, JobRole.DEVELOPER)
    assert top == ["#기술리서치", "#API연동", "#디버깅"]


def test_v2_postscore_select_top3_respects_role_switch() -> None:
    """같은 후보 list 라도 직군 바뀌면 다른 top3 가 나온다 (가중치가 도메인 점수)."""
    # PLANNER 기준:
    #   #기술리서치=Mid(2) · #UX설계=High(3) · #API연동=Low(1) · #디버깅=Low(1)
    #   · #비주얼디자인=Low(1) · #피드백수용=High(3)
    # → top3: #UX설계(3, idx 1) · #피드백수용(3, idx 5) · #기술리서치(2, idx 0)
    candidates = ["#기술리서치", "#UX설계", "#API연동", "#디버깅", "#비주얼디자인", "#피드백수용"]
    top = _v2_select_top3(candidates, JobRole.PLANNER)
    assert top == ["#UX설계", "#피드백수용", "#기술리서치"]


def test_v2_postscore_select_top3_handles_fewer_than_three_candidates() -> None:
    """후보가 3개 미만이면 그 갯수 그대로 정렬해 반환."""
    candidates = ["#UX설계", "#기술리서치"]
    top = _v2_select_top3(candidates, JobRole.DEVELOPER)
    # 개발자 점수: UX설계=1, 기술리서치=3 → 기술리서치가 먼저
    assert top == ["#기술리서치", "#UX설계"]


def test_v2_postscore_accepts_cross_category_candidates() -> None:
    """카테고리 좁힘 제거 — 풀 전체에서 자유롭게 선택 가능.

    프롬프트 명세 "카테고리 무관, 풀 전체 열려 있다" 와 정합. eval_set_v2 의
    must/accept 가 selectedCompetency 외 카테고리 태그도 자유롭게 섞는 구조라
    카테고리 좁힘이 남아 있으면 정상 응답이 풀-외로 reject 된다 (regression guard).
    """
    # 5 tags spanning 발견·분석 + 협업·조율 + 문제해결·개선 + 기획·실행
    raw = '{"detailTags": ["#트렌드리서치","#의견조율","#원인분석","#디버깅","#기술리서치"]}'
    assert _v2_parse_and_validate(raw) == [
        "#트렌드리서치",
        "#의견조율",
        "#원인분석",
        "#디버깅",
        "#기술리서치",
    ]


# === /v1/tagging — 로그 PII 안전성 (검증 실패 path) ===


@respx.mock
def test_v1_tagging_does_not_log_star_body_on_validation_failure(
    client: TestClient, token: str, caplog: pytest.LogCaptureFixture
) -> None:
    respx.post(ANTHROPIC_URL).mock(
        side_effect=[
            Response(200, json=_anthropic_msg('"detailTags": ["#없는1"]}')),
            Response(200, json=_anthropic_msg('"detailTags": ["#없는2"]}')),
        ]
    )
    caplog.set_level(logging.INFO)
    r = client.post("/v1/tagging", json=_PAYLOAD, headers={"X-Internal-Token": token})
    assert r.status_code == 422
    _assert_no_pii_in_logs(caplog)
