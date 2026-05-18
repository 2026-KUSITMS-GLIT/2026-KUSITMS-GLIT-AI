"""Tagging v2_postscore — v1 의 한계를 종합 해소한 두 번째 variant.

v1_baseline 대비 변경점 세 가지를 한 묶음으로 도입:

1. **백틱 strip 정규식 확장** — back-ref ``\\1`` 로 1·2·3개 백틱(양 끝 동일 개수) 모두 매치.
   v1 실측에서 Haiku 가 응답을 single backtick(``` `...` ```)으로 감싸는 빈도가 높아
   corrective 재시도가 자주 발동했음 (experiments/tagging/2026-05-17_v1_baseline.md §1).

2. **가중치 표를 LLM 프롬프트에서 제거** — 프롬프트 약 1,500 tok 절감. LLM 은 본문 근거
   강한 순으로 5~7개 후보만 출력하고, 우리 코드가 :func:`tag_score` 로 직군 가중치
   점수를 매겨 상위 3개로 자른다 (deterministic 후처리, 가중치 튜닝이 코드 단위로 가능).

3. **프롬프트 일반 정리** — 가중치 표 제거에 맞춰 직군 우선순위 규칙도 빼고, 출력 갯수
   5~7개로 변경.

v3 부터는 본 v2 의 데이터/흐름을 기준으로 추가 개선 (research_ref §2-2 의 v2 개선 조건 — 운영
데이터 오분류 패턴 누적 후 fewshot 등) 검토.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import orjson

from app.core.logging import get_logger
from app.schemas.common import (
    JOB_ROLE_LABELS_KO,
    PRIMARY_CATEGORY_LABELS_KO,
    JobRole,
    PrimaryCategory,
)
from app.schemas.tagging import TaggingRequest, TaggingResponse
from app.services._clients.llm_client import LLMClient, WorkloadType
from app.services.tagging.data import ALL_TAGS, TAGS_BY_CATEGORY, tag_score
from app.services.tagging.exceptions import TaggingValidationError
from app.services.tagging.v1_baseline import _extract_text

logger = get_logger(__name__)


_PROMPT_PATH = Path(__file__).parents[2] / "prompts" / "tagging" / "v2_postscore.md"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")


# v1 대비 변경점 ① — 1·2·3개 백틱(양 끝 동일 개수) 모두 매치.
_CODE_FENCE_RE = re.compile(r"^(`{1,3})(?:json)?\s*\n?(.*?)\n?\s*\1$", re.DOTALL)


_CANDIDATE_MIN = 5
_CANDIDATE_MAX = 7
"""LLM 에게 요청하는 후보 갯수 범위. 후처리에서 상위 3개로 자른다."""

_FINAL_TOP = 3
"""최종 응답에 노출하는 태그 갯수. ``TaggingResponse.detail_tags`` 의 max."""


_USER_TRIGGER = (
    f"위 지침에 따라 detailTags {_CANDIDATE_MIN}~{_CANDIDATE_MAX}개를 JSON 한 줄로 출력해."
)


_MAX_TOKENS = 250
"""v1 의 200 보다 +50 — 후보가 5~7개라 output 토큰 약간 증가."""


_TOKEN_RE = re.compile(r"\{(jobRole|primaryCategory|situationTask|action|result)\}")
"""프롬프트 템플릿의 치환 토큰 — 1패스 ``re.sub`` 로만 매치된다."""


def _render_prompt(req: TaggingRequest) -> str:
    """변수 토큰을 한글 라벨/STAR 본문으로 치환한 시스템 프롬프트를 반환.

    1패스 정규식 치환 — 사용자 본문에 ``{result}`` 같은 토큰 문자열이 섞여도
    재치환되지 않는다. STAR 본문은 ``<situationTask>...</situationTask>`` 등
    XML-like 태그로 경계화해 프롬프트 인젝션 저항성을 높인다.
    """
    values = {
        "jobRole": JOB_ROLE_LABELS_KO[req.job_role],
        "primaryCategory": PRIMARY_CATEGORY_LABELS_KO[req.selected_competency],
        "situationTask": f"<situationTask>\n{req.situation_task}\n</situationTask>",
        "action": f"<action>\n{req.action}\n</action>",
        "result": f"<result>\n{req.result}\n</result>",
    }
    return _TOKEN_RE.sub(lambda m: values[m.group(1)], _PROMPT_TEMPLATE)


def _strip_code_fence(text: str) -> str:
    """LLM 이 백틱(1~3개)으로 감쌌으면 벗긴 본문 반환, 아니면 그대로."""
    m = _CODE_FENCE_RE.match(text)
    if m:
        return m.group(2).strip()
    return text


def _allowed_tags_for(category: PrimaryCategory) -> frozenset[str]:
    """선택된 ``primaryCategory`` 안에서 허용되는 태그 셋.

    카테고리 외 태그를 후보 단계에서 걸러내 contract (선택 역량 내 태그만 출력)
    를 보장한다.
    """
    return TAGS_BY_CATEGORY[category]


def _parse_and_validate(raw: str, allowed_tags: frozenset[str] = ALL_TAGS) -> list[str]:
    """후보 검증 — 갯수 :data:`_CANDIDATE_MIN`~:data:`_CANDIDATE_MAX`, 풀 내, 중복 X.

    실패 시 :class:`TaggingValidationError`. 후처리에서 ``_FINAL_TOP`` 으로 자르므로
    여기서는 후보 단계 갯수만 검증한다. ``allowed_tags`` 는 카테고리별 허용 셋을
    좁혀 넘길 수 있다 (기본 ``ALL_TAGS``).
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

    if not _CANDIDATE_MIN <= len(str_tags) <= _CANDIDATE_MAX:
        raise TaggingValidationError(
            f"detailTags 후보 갯수 위반: {len(str_tags)} (허용 {_CANDIDATE_MIN}~{_CANDIDATE_MAX})"
        )

    if len(set(str_tags)) != len(str_tags):
        raise TaggingValidationError("detailTags 중복 포함")

    out_of_pool = [t for t in str_tags if t not in allowed_tags]
    if out_of_pool:
        raise TaggingValidationError(f"허용 태그 풀 외 태그 포함: {out_of_pool}")

    return str_tags


def _select_top3(candidates: list[str], role: JobRole) -> list[str]:
    """직군 가중치 점수 내림차순으로 상위 :data:`_FINAL_TOP` 개를 선택.

    동점 처리: LLM 응답 순서 우선 (배열 앞쪽 = 본문 근거 강하다는 프롬프트 약속).

    sort key 는 ``(-score, index)`` ascending — score 높은 순, 같은 score 면 index 작은 순.
    """
    scored = sorted((-tag_score(t, role), i, t) for i, t in enumerate(candidates))
    return [t for _, _, t in scored[:_FINAL_TOP]]


def _build_corrective_user_message(reason: str) -> str:
    """2차 시도용 corrective user 메시지."""
    return (
        f"이전 응답이 형식에 맞지 않다. 이유: {reason}. "
        f"다시 시도해. 반드시 시스템 프롬프트의 태그 풀 안에서만 "
        f"{_CANDIDATE_MIN}~{_CANDIDATE_MAX}개 골라야 하고, "
        '`{"detailTags": ["#태그A", "#태그B", "#태그C", "#태그D", "#태그E"]}` 같은 '
        "한 줄 JSON 만 출력. 코드블록(```)·도입어·primaryCategory 키 모두 금지."
    )


async def run(req: TaggingRequest, llm: LLMClient, model: str) -> TaggingResponse:
    """Tagging v2_postscore 실행."""
    system = _render_prompt(req)
    allowed = _allowed_tags_for(req.selected_competency)
    log_ctx: dict[str, Any] = {
        "job_role": req.job_role.value,
        "primary_category": req.selected_competency.value,
    }

    first_msg = await llm.create_message(
        workload=WorkloadType.TAGGING,
        model=model,
        system=system,
        messages=[{"role": "user", "content": _USER_TRIGGER}],
        max_tokens=_MAX_TOKENS,
    )
    first_raw = _extract_text(first_msg.content)

    try:
        candidates = _parse_and_validate(first_raw, allowed)
    except TaggingValidationError as first_err:
        logger.warning(
            "tagging.validation_failed",
            extra={**log_ctx, "attempt": 1, "reason": str(first_err)},
        )
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
            candidates = _parse_and_validate(retry_raw, allowed)
        except TaggingValidationError as retry_err:
            logger.warning(
                "tagging.validation_failed",
                extra={**log_ctx, "attempt": 2, "reason": str(retry_err)},
            )
            raise

    selected = _select_top3(candidates, req.job_role)
    logger.info(
        "tagging.done",
        extra={**log_ctx, "candidate_count": len(candidates), "tag_count": len(selected)},
    )
    return TaggingResponse(
        primary_category=req.selected_competency,
        detail_tags=selected,
    )
