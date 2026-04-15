"""Structured logging setup."""

from __future__ import annotations

import logging
import sys
from logging.config import dictConfig

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
                    "datefmt": "%Y-%m-%dT%H:%M:%S%z",
                },
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": "default",
                },
            },
            "loggers": {
                "uvicorn": {"level": settings.log_level, "propagate": True},
                "uvicorn.access": {"level": settings.log_level, "propagate": True},
                "httpx": {"level": "WARNING", "propagate": True},
            },
            "root": {
                "level": settings.log_level,
                "handlers": ["stdout"],
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
