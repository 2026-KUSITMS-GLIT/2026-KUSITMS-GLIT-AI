"""리포트 생성 엔드포인트 — 인증 / 스키마 검증 / 더미 응답 테스트."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# ── 공용 더미 요청 바디 ──────────────────────────────────────────────────────

_RECORD = {
    "starRecordId": 1,
    "situationTask": "복수의 이해관계자 요구가 충돌하는 상황에서 기획 방향을 잡아야 했습니다.",
    "action": "전체 흐름을 구조화해 PRD와 기능명세서를 작성했습니다.",
    "result": "단기간에 이해관계자 합의를 이끌어냈습니다.",
    "completedAt": "2026-04-09",
    "competency": "PLANNING_EXECUTION",
    "detailTags": ["#기획_구조화", "#서비스_기획"],
}

_SCRUM_ITEM = {
    "projectName": "KOPLE",
    "scrumTitle": "PRD 초안 작성",
    "content": "PRD와 기능명세서 완성.",
    "starRecordId": 1,
}

_BASE_BODY: dict = {
    "nickname": "글릿",
    "job": "PLANNER",
    "status": "JOB_SEEKER",
    "records": [_RECORD] * 10,
    "scrumsByDate": [{"date": "2026-04-09", "scrums": [_SCRUM_ITEM]}],
    "recordPeriod": {"from": "2026-01-01", "to": "2026-04-10"},
    "totalCount": 10,
}


# ── /api/reports/* 인증 테스트 ───────────────────────────────────────────────


class TestApiAuth:
    """/api/reports/* 전체에 X-Internal-Token 보호가 걸려있는지 검증."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/reports/mini",
            "/api/reports/career/branding",
            "/api/reports/career/narrative",
            "/api/reports/career/strengths-and-interview",
            "/api/reports/career/highlights",
        ],
    )
    def test_no_token_returns_401(self, client: TestClient, path: str) -> None:
        r = client.post(path, json=_BASE_BODY)
        assert r.status_code == 401

    @pytest.mark.parametrize(
        "path",
        [
            "/api/reports/mini",
            "/api/reports/career/branding",
            "/api/reports/career/narrative",
            "/api/reports/career/strengths-and-interview",
            "/api/reports/career/highlights",
        ],
    )
    def test_wrong_token_returns_403(self, client: TestClient, path: str) -> None:
        r = client.post(path, json=_BASE_BODY, headers={"X-Internal-Token": "wrong"})
        assert r.status_code == 403


# ── /api/reports/* 더미 응답 테스트 ─────────────────────────────────────────


class TestApiMiniReport:
    """POST /api/reports/mini — 더미 200 응답."""

    def test_returns_200_with_valid_body(self, client: TestClient, token: str) -> None:
        r = client.post("/api/reports/mini", json=_BASE_BODY, headers={"X-Internal-Token": token})
        assert r.status_code == 200
        data = r.json()
        assert "activitySummary" in data
        assert "nextFocusPoint" in data
        assert "competencyFrequency" in data
        assert isinstance(data["competencyFrequency"], list)
        assert "topDetailTags" in data
        assert isinstance(data["topDetailTags"], list)

    def test_missing_required_field_returns_422(self, client: TestClient, token: str) -> None:
        body = {**_BASE_BODY}
        body.pop("job")
        r = client.post("/api/reports/mini", json=body, headers={"X-Internal-Token": token})
        assert r.status_code == 422

    def test_invalid_job_value_returns_422(self, client: TestClient, token: str) -> None:
        body = {**_BASE_BODY, "job": "INVALID_JOB"}
        r = client.post("/api/reports/mini", json=body, headers={"X-Internal-Token": token})
        assert r.status_code == 422


class TestApiCareerBranding:
    """POST /api/reports/career/branding — 더미 200 응답."""

    def test_returns_200_with_valid_body(self, client: TestClient, token: str) -> None:
        r = client.post(
            "/api/reports/career/branding",
            json=_BASE_BODY,
            headers={"X-Internal-Token": token},
        )
        assert r.status_code == 200
        data = r.json()
        assert "brandingStatement" in data
        assert "brandingPattern" in data
        assert "topDetailTags" in data
        assert isinstance(data["topDetailTags"], list)


class TestApiCareerNarrative:
    """POST /api/reports/career/narrative — 더미 200 응답."""

    def test_returns_200_with_valid_body(self, client: TestClient, token: str) -> None:
        r = client.post(
            "/api/reports/career/narrative",
            json=_BASE_BODY,
            headers={"X-Internal-Token": token},
        )
        assert r.status_code == 200
        assert "narrativeSummary" in r.json()


class TestApiCareerStrengthsAndInterview:
    """POST /api/reports/career/strengths-and-interview — 더미 200 응답."""

    def test_returns_200_with_valid_body(self, client: TestClient, token: str) -> None:
        r = client.post(
            "/api/reports/career/strengths-and-interview",
            json=_BASE_BODY,
            headers={"X-Internal-Token": token},
        )
        assert r.status_code == 200
        data = r.json()
        assert "strengths" in data
        assert 2 <= len(data["strengths"]) <= 3
        for s in data["strengths"]:
            assert "title" in s
            assert "description" in s
            assert "evidences" in s
        assert "interviewQuestions" in data
        assert 2 <= len(data["interviewQuestions"]) <= 3
        for q in data["interviewQuestions"]:
            assert "question" in q
            assert "evidences" in q


class TestApiCareerHighlights:
    """POST /api/reports/career/highlights — 더미 200 응답."""

    def test_returns_200_with_valid_body(self, client: TestClient, token: str) -> None:
        r = client.post(
            "/api/reports/career/highlights",
            json=_BASE_BODY,
            headers={"X-Internal-Token": token},
        )
        assert r.status_code == 200
        data = r.json()
        assert "experienceHighlights" in data
        assert 2 <= len(data["experienceHighlights"]) <= 3


# ── /v1/reports/* 실험 경로 테스트 ──────────────────────────────────────────


class TestV1Reports:
    """/v1/reports/* — 서비스 레이어 연동 및 인증 검증."""

    def test_mini_no_token_returns_401(self, client: TestClient) -> None:
        r = client.post("/v1/reports/mini", json=_BASE_BODY)
        assert r.status_code == 401

    def test_mini_wrong_token_returns_403(self, client: TestClient) -> None:
        r = client.post(
            "/v1/reports/mini",
            json=_BASE_BODY,
            headers={"X-Internal-Token": "wrong"},
        )
        assert r.status_code == 403

    def test_mini_returns_200(self, client: TestClient, token: str) -> None:
        r = client.post(
            "/v1/reports/mini",
            json=_BASE_BODY,
            headers={"X-Internal-Token": token},
        )
        assert r.status_code == 200
        data = r.json()
        assert "activitySummary" in data
        assert "nextFocusPoint" in data
        assert "competencyFrequency" in data
        assert "topDetailTags" in data

    def test_strengths_and_interview_returns_200(self, client: TestClient, token: str) -> None:
        r = client.post(
            "/v1/reports/career/strengths-and-interview",
            json=_BASE_BODY,
            headers={"X-Internal-Token": token},
        )
        assert r.status_code == 200
        data = r.json()
        assert "strengths" in data
        assert "interviewQuestions" in data
