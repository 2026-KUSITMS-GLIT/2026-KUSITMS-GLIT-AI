"""Tagging v1_baseline 구현 — zero-shot 분류기.

흐름:
    1) ``v1_baseline.md`` 시스템 프롬프트에 변수 치환
    2) ``LLMClient.create_message(workload=TAGGING)`` 호출
    3) 응답 텍스트에서 코드블록 제거 → JSON 파싱 → 풀/갯수/중복 검증
    4) 검증 실패 시 corrective prompt(이전 응답 echo + 형식 교정 지시)로 1회 재시도
    5) 두 시도 모두 실패하면 :class:`TaggingValidationError` raise.

LLM 호출 단계의 실패(:mod:`LLMError` 하위)는 그대로 propagate 되며, 라우터에서
HTTP 상태코드로 변환한다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import orjson

from app.core.logging import get_logger
from app.schemas.common import JOB_ROLE_LABELS_KO, PRIMARY_CATEGORY_LABELS_KO
from app.schemas.tagging import TaggingRequest, TaggingResponse
from app.services._clients.llm_client import LLMClient, WorkloadType
from app.services.tagging.data import ALL_TAGS
from app.services.tagging.exceptions import TaggingValidationError

logger = get_logger(__name__)


_PROMPT_PATH = Path(__file__).parents[2] / "prompts" / "tagging" / "v1_baseline.md"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")
"""모듈 로드 시 1회 read 한 시스템 프롬프트 템플릿."""


_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)
"""LLM 이 실수로 `````json ... ````` 으로 감쌌을 때 벗기는 정규식."""


_USER_TRIGGER = "위 지침에 따라 detailTags JSON 한 줄을 출력해."
"""1차 user 메시지. Anthropic API 가 messages 1개 이상을 요구하므로 트리거용으로 단 한 줄."""


_MAX_TOKENS = 200
"""tagging 응답은 짧으니 출력 토큰을 빠듯하게."""


def _render_prompt(req: TaggingRequest) -> str:
    """변수 토큰을 한글 라벨/STAR 본문으로 치환한 시스템 프롬프트를 반환.

    JSON 예시의 중괄호와 충돌하지 않도록 ``.format()`` 이 아닌 ``.replace()`` 를 쓴다.
    """
    return (
        _PROMPT_TEMPLATE.replace("{jobRole}", JOB_ROLE_LABELS_KO[req.job_role])
        .replace("{primaryCategory}", PRIMARY_CATEGORY_LABELS_KO[req.selected_competency])
        .replace("{situationTask}", req.situation_task)
        .replace("{action}", req.action)
        .replace("{result}", req.result)
    )


def _extract_text(content: Any) -> str:
    """Anthropic Message ``content`` 블록에서 텍스트만 모아 strip 후 반환.

    tool_use 등 텍스트가 아닌 블록은 무시한다. 모델이 텍스트를 여러 블록으로 쪼개
    낼 가능성에 대비해 join 한다.
    """
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts).strip()


def _strip_code_fence(text: str) -> str:
    """LLM 이 코드블록으로 감쌌으면 벗긴 본문을 반환, 아니면 그대로."""
    m = _CODE_FENCE_RE.match(text)
    if m:
        return m.group(1).strip()
    return text


def _parse_and_validate(raw: str) -> list[str]:
    """LLM 응답 텍스트 → 검증된 ``detail_tags`` 리스트.

    형식·갯수·중복·풀 외 태그 모두 검사. 실패 시 :class:`TaggingValidationError`.
    """
    text = _strip_code_fence(raw)
    try:
        payload = orjson.loads(text)
    except orjson.JSONDecodeError as exc:
        raise TaggingValidationError(f"JSON 파싱 실패: {exc}") from exc

    if not isinstance(payload, dict):
        raise TaggingValidationError("응답이 JSON object 가 아님")

    tags = payload.get("detailTags")
    if not isinstance(tags, list):
        raise TaggingValidationError("detailTags 가 배열이 아니거나 누락")

    if not all(isinstance(t, str) for t in tags):
        raise TaggingValidationError("detailTags 에 문자열 아닌 원소 포함")

    str_tags: list[str] = list(tags)

    if not 1 <= len(str_tags) <= 3:
        raise TaggingValidationError(f"detailTags 갯수 위반: {len(str_tags)} (허용 1~3)")

    if len(set(str_tags)) != len(str_tags):
        raise TaggingValidationError("detailTags 중복 포함")

    out_of_pool = [t for t in str_tags if t not in ALL_TAGS]
    if out_of_pool:
        raise TaggingValidationError(f"태그 풀 외 태그 포함: {out_of_pool}")

    return str_tags


def _build_corrective_user_message(reason: str) -> str:
    """2차 시도용 corrective user 메시지."""
    return (
        f"이전 응답이 형식에 맞지 않다. 이유: {reason}. "
        "다시 시도해. 반드시 시스템 프롬프트의 태그 풀 안에서만 1~3개 골라야 하고, "
        '`{"detailTags": ["#태그A"]}` 같은 한 줄 JSON 만 출력. '
        "코드블록(```)·도입어·primaryCategory 키 모두 금지."
    )


async def run(req: TaggingRequest, llm: LLMClient, model: str) -> TaggingResponse:
    """Tagging v1_baseline 실행 (1회 corrective 재시도 포함).

    Args:
        req: 검증된 :class:`TaggingRequest`.
        llm: lifespan 에서 생성된 :class:`LLMClient` 싱글턴.
        model: 사용할 Claude 모델명 (``Settings.anthropic_model``).

    Returns:
        :class:`TaggingResponse` — ``primaryCategory`` 는 요청 echo,
        ``detailTags`` 는 검증을 통과한 1~3개 태그.

    Raises:
        TaggingValidationError: 두 시도 모두 응답 형식·내용을 만족하지 못한 경우.
        LLMError (혹은 하위): LLM 호출 단계의 실패는 :class:`LLMClient` 가 매핑해 던지며,
            여기서는 그대로 propagate.
    """
    system = _render_prompt(req)
    log_ctx = {
        "job_role": req.job_role.value,
        "primary_category": req.selected_competency.value,
    }

    # 1차 시도
    first_msg = await llm.create_message(
        workload=WorkloadType.TAGGING,
        model=model,
        system=system,
        messages=[{"role": "user", "content": _USER_TRIGGER}],
        max_tokens=_MAX_TOKENS,
    )
    first_raw = _extract_text(first_msg.content)

    try:
        tags = _parse_and_validate(first_raw)
    except TaggingValidationError as first_err:
        logger.warning(
            "tagging.validation_failed",
            extra={**log_ctx, "attempt": 1, "reason": str(first_err)},
        )
        # 2차 시도 — corrective
        retry_msg = await llm.create_message(
            workload=WorkloadType.TAGGING,
            model=model,
            system=system,
            messages=[
                {"role": "user", "content": _USER_TRIGGER},
                {"role": "assistant", "content": first_raw},
                {"role": "user", "content": _build_corrective_user_message(str(first_err))},
            ],
            max_tokens=_MAX_TOKENS,
        )
        retry_raw = _extract_text(retry_msg.content)
        try:
            tags = _parse_and_validate(retry_raw)
        except TaggingValidationError as retry_err:
            logger.warning(
                "tagging.validation_failed",
                extra={**log_ctx, "attempt": 2, "reason": str(retry_err)},
            )
            raise

    logger.info("tagging.done", extra={**log_ctx, "tag_count": len(tags)})
    return TaggingResponse(
        primary_category=req.selected_competency,
        detail_tags=tags,
    )
