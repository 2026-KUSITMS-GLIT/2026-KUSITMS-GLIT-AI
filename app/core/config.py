"""Application settings — loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_TOKEN_DEFAULTS = {
    "",
    "change-me-to-a-random-32-byte-token",
}
"""prod 환경에서 거부할 INTERNAL_API_TOKEN 플레이스홀더 값 집합.

``.env.example`` 의 안내 문자열과 빈 문자열이 포함된다. 이 중 하나라도 prod 에서
주입되면 검증 단계에서 raise 되어 부팅이 중단된다. Settings 자체에는 기본값을 두지
않으므로 ``.env`` / SSM 에 값이 없으면 애초에 ``ValidationError`` 로 부팅이 실패한다.
"""

_MIN_TOKEN_LENGTH = 32
"""prod 환경 INTERNAL_API_TOKEN 의 최소 길이 (문자 기준).

``secrets.token_urlsafe(24)`` 가 정확히 32자를 반환하므로, 이 값을 만족하려면
최소 24바이트(192비트) 의 엔트로피가 필요하다. 사고로 짧은 값(``asdf`` 등) 이
주입되는 것을 막는 얕은 엔트로피 가드 역할이다.
"""


class Settings(BaseSettings):
    """All runtime configuration. Mutate via env vars, never in code.

    새 설정이 필요하면 여기에 필드를 추가하고 `.env.example`에도 같은 키를 문서화한다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Server ----
    app_env: Literal["local", "dev", "staging", "prod"] = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ---- Auth ----
    internal_api_token: str = Field(
        description=(
            "Spring Boot 백엔드와 공유하는 내부 토큰. "
            "기본값 없음 — .env 또는 SSM 에서 반드시 주입되어야 한다."
        ),
    )

    @model_validator(mode="after")
    def _require_secure_token_in_prod(self) -> Settings:
        """prod 환경에서 ``INTERNAL_API_TOKEN`` 이 안전한 값인지 검증한다.

        SSM 주입 누락이나 플레이스홀더 그대로 배포되는 사고를 막기 위한 부팅 시 가드.
        ``APP_ENV=prod`` 이면 두 단계 검사를 거친다.

        1. :data:`_INSECURE_TOKEN_DEFAULTS` 중 하나면 실패 (플레이스홀더 탐지).
        2. 길이가 :data:`_MIN_TOKEN_LENGTH` 미만이면 실패 (엔트로피 가드).

        로컬 환경에서는 어떤 값이든 (기본값 포함) 통과한다.

        Returns:
            검증이 통과한 자기 자신 (pydantic after-validator 규약).

        Raises:
            ValueError: prod 에서 플레이스홀더 값이거나 길이가 부족한 경우.
        """
        if self.app_env != "prod":
            return self
        if self.internal_api_token in _INSECURE_TOKEN_DEFAULTS:
            raise ValueError(
                "APP_ENV=prod 에서는 INTERNAL_API_TOKEN 을 "
                "기본값이 아닌 실제 값으로 설정해야 합니다"
            )
        if len(self.internal_api_token) < _MIN_TOKEN_LENGTH:
            raise ValueError(
                f"APP_ENV=prod 에서는 INTERNAL_API_TOKEN 이 최소 "
                f"{_MIN_TOKEN_LENGTH}자 이상이어야 합니다 "
                "(생성 예: python -c 'import secrets; print(secrets.token_urlsafe(32))')"
            )
        return self

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
