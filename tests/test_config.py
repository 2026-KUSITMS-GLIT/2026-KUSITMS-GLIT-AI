"""``Settings`` 검증 — prod 가드 (플레이스홀더 / 최소 길이) 및 필수 필드."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


class TestLocalEnv:
    """로컬에서는 prod 가드가 걸리지 않아 어떤 값이든 허용된다."""

    def test_short_token_passes(self) -> None:
        s = Settings(app_env="local", internal_api_token="short")
        assert s.internal_api_token == "short"
        assert s.is_prod is False

    def test_placeholder_passes_in_local(self) -> None:
        # prod 전용 가드이므로 로컬에서는 플레이스홀더도 통과해야 한다.
        s = Settings(
            app_env="local",
            internal_api_token="change-me-to-a-random-32-byte-token",
        )
        assert s.app_env == "local"


class TestProdPlaceholderGuard:
    """prod 에서는 플레이스홀더/빈 값 주입 시 부팅 실패."""

    @pytest.mark.parametrize(
        "bad_token",
        ["", "change-me-to-a-random-32-byte-token"],
    )
    def test_rejected(self, bad_token: str) -> None:
        with pytest.raises(ValidationError, match="기본값이 아닌 실제 값"):
            Settings(app_env="prod", internal_api_token=bad_token)


class TestProdLengthGuard:
    """prod 에서는 토큰이 최소 32자 이상이어야 한다."""

    @pytest.mark.parametrize("length", [1, 16, 31])
    def test_short_rejected(self, length: int) -> None:
        with pytest.raises(ValidationError, match="최소 32자"):
            Settings(app_env="prod", internal_api_token="x" * length)

    def test_boundary_32_passes(self) -> None:
        s = Settings(app_env="prod", internal_api_token="x" * 32)
        assert s.is_prod is True

    def test_long_token_passes(self) -> None:
        s = Settings(app_env="prod", internal_api_token="A1b" * 20)  # 60자
        assert s.is_prod is True


class TestRequiredField:
    """기본값 없음 — .env / SSM 둘 다 없으면 ``ValidationError``."""

    def test_missing_raises_validation_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # 작업 디렉토리를 임시 경로로 바꿔 리포의 `.env` 가 안 읽히게 한다.
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
        with pytest.raises(ValidationError, match="internal_api_token"):
            Settings()
