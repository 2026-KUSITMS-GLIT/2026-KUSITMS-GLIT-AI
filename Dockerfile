# syntax=docker/dockerfile:1.7

# =========================
# Stage 1 — builder (uv sync)
# =========================
FROM python:3.12-slim-bookworm AS builder

# uv는 별도 이미지에서 바이너리만 복사 (버전 고정)
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 의존성 먼저 설치 — 코드 변경 시 캐시 재사용
COPY pyproject.toml ./
# uv.lock은 있으면 복사 (없어도 빌드 실패하지 않도록 glob)
COPY uv.loc[k] ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project

COPY app ./app


# =========================
# Stage 2 — runtime (slim)
# =========================
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# curl은 컨테이너 HEALTHCHECK / 디버깅용 — 불필요하면 제거 가능
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 1001 app \
 && useradd --system --uid 1001 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/app   /app/app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
