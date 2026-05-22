"""공용 pytest 픽스처.

모든 테스트는 ``autouse`` 픽스처 덕분에 깨끗한 env (``APP_ENV=local``,
유효한 ``INTERNAL_API_TOKEN``) 와 비워진 Settings 캐시 위에서 돈다.
FastAPI 앱 전체를 부팅해 lifespan 까지 도는 ``client`` 픽스처를 함께 제공한다.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

# app.main 임포트 전에 필수 환경변수를 주입 — CI처럼 .env가 없는 환경에서도 동작하도록.
_TEST_TOKEN = "test-token-" + "a" * 32
os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault("INTERNAL_API_TOKEN", _TEST_TOKEN)

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """각 테스트에 공통 env 를 주입하고 Settings lru_cache 를 리셋한다.

    ``TAGGING_VARIANT`` 도 명시적으로 핀 — 로컬 ``.env`` 와 CI(.env 없음) 간 활성
    variant 가 달라져 테스트 결과가 갈리는 사고를 막는다 (CI 는 default ``v1_baseline``
    으로 떨어졌지만 로컬은 ``v2_postscore`` 였던 잠재 디바이드).
    """
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("INTERNAL_API_TOKEN", _TEST_TOKEN)
    monkeypatch.setenv("TAGGING_VARIANT", "v2_postscore")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def token() -> str:
    """테스트 전역에서 공유하는 유효 토큰 — ``_clean_settings`` 가 주입한 값과 같다."""
    return _TEST_TOKEN


@pytest.fixture
def client() -> Iterator[TestClient]:
    """전체 앱을 부팅해 lifespan 이벤트까지 도는 ``TestClient``."""
    with TestClient(app) as c:
        yield c
