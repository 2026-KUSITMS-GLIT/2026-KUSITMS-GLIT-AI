"""Application settings — loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_TOKEN_DEFAULTS = {
    "",
    "dev-insecure-token",
    "change-me-to-a-random-32-byte-token",
}
"""prod 환경에서 거부할 INTERNAL_API_TOKEN 기본/플레이스홀더 값 집합.

Settings 기본값, ``.env.example`` 템플릿 값, 빈 문자열이 포함된다.
이 중 하나라도 prod 에서 주입되면 검증 단계에서 raise 되어 부팅이 중단된다.
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
        default="dev-insecure-token",
        description="Shared secret between Spring Boot backend and this AI service.",
    )

    @model_validator(mode="after")
    def _require_secure_token_in_prod(self) -> Settings:
        """prod 환경에서 ``INTERNAL_API_TOKEN`` 이 안전한 값인지 검증한다.

        SSM 주입 누락이나 플레이스홀더 그대로 배포되는 사고를 막기 위한 부팅 시 가드.
        ``APP_ENV=prod`` 이면서 토큰이 :data:`_INSECURE_TOKEN_DEFAULTS` 중 하나라면
        부팅을 실패시킨다. 로컬 환경에서는 기본값으로 그대로 통과한다.

        Returns:
            검증이 통과한 자기 자신 (pydantic after-validator 규약).

        Raises:
            ValueError: prod 에서 기본값/빈 문자열 토큰이 감지된 경우.
        """
        if self.app_env == "prod" and self.internal_api_token in _INSECURE_TOKEN_DEFAULTS:
            raise ValueError(
                "APP_ENV=prod 에서는 INTERNAL_API_TOKEN 을 "
                "기본값이 아닌 실제 값으로 설정해야 합니다"
            )
        return self

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
