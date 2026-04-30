"""Structured logging setup.

prod 에서는 한 줄 JSON, 그 외(local 등)에서는 사람이 읽기 편한 텍스트 포맷으로 내보낸다.
``configure_logging()`` 은 앱 lifespan startup 에서 단 한 번 호출한다.
"""

from __future__ import annotations

import logging
import sys
from logging.config import dictConfig
from typing import Any

import orjson

from app.core.config import get_settings

_RESERVED_LOGRECORD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)
"""``LogRecord`` 의 고정 속성 집합.

JSON 직렬화 시 이 키들은 기본 필드(``ts``, ``level``, ``logger``, ``msg``, ``exc``) 로
이미 투영되므로 ``extra`` 병합 단계에서 중복 방지용으로 제외한다.
"""


class JsonFormatter(logging.Formatter):
    """한 줄 JSON 으로 ``LogRecord`` 를 직렬화하는 포매터.

    CloudWatch / ELK 등에서 파싱하기 쉽도록 고정 필드와
    ``logger.info("...", extra={...})`` 로 실어 보낸 키를 한 객체에 평탄화한다.

    Example:
        >>> logger.info("tagging.done", extra={"user_id": 42, "latency_ms": 128})
        {"ts": "...", "level": "INFO", "logger": "app.services.tagging",
         "msg": "tagging.done", "user_id": 42, "latency_ms": 128}
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOGRECORD_ATTRS or key.startswith("_"):
                continue
            payload[key] = value
        return orjson.dumps(payload, default=str).decode()


def configure_logging() -> None:
    """전역 로깅 구성을 초기화한다.

    - ``APP_ENV=prod`` 이면 :class:`JsonFormatter`, 그 외에는 사람이 읽기 편한 텍스트 포맷.
    - 모든 로그는 stdout 으로만 내보낸다 (컨테이너/uvicorn 환경 친화).
    - uvicorn 이 기본적으로 붙이는 핸들러를 비워 root 한 곳에서만 출력되도록 중복을 제거한다.

    앱 ``lifespan`` startup 에서 단 한 번 호출한다. 여러 번 호출해도 치명적이진 않지만,
    :func:`logging.config.dictConfig` 가 기존 구성을 덮어쓰므로 불필요한 비용이다.
    """
    settings = get_settings()
    formatter_key = "json" if settings.is_prod else "text"

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "text": {
                    "format": "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
                    "datefmt": "%Y-%m-%dT%H:%M:%S%z",
                },
                "json": {
                    "()": JsonFormatter,
                },
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": formatter_key,
                },
            },
            "loggers": {
                "uvicorn": {"handlers": [], "level": settings.log_level, "propagate": True},
                "uvicorn.error": {"handlers": [], "level": settings.log_level, "propagate": True},
                "uvicorn.access": {"handlers": [], "level": settings.log_level, "propagate": True},
                "httpx": {"handlers": [], "level": "WARNING", "propagate": True},
            },
            "root": {
                "level": settings.log_level,
                "handlers": ["stdout"],
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    """모듈 수준 logger 를 가져오는 얇은 헬퍼.

    규약: 호출부는 ``get_logger(__name__)`` 로 받고, 메시지는 ``domain.action``
    패턴 (``tagging.done``, ``report.failed``) 으로 쓴다. 동적 값은 문자열에 끼워 넣지 말고
    ``extra={"key": value}`` 로 실어 보내면 JSON 포맷에서 최상위 필드로 노출된다.

    Args:
        name: 보통 ``__name__``.

    Returns:
        전역 로깅 설정을 공유하는 :class:`logging.Logger`.
    """
    return logging.getLogger(name)
