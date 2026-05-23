"""리포트 생성 서비스 v1 baseline — Claude API 구현."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import orjson

from app.core.logging import get_logger
from app.schemas.common import JOB_ROLE_LABELS_KO
from app.schemas.report import (
    AiCareerBrandingResponse,
    AiCareerHighlightsResponse,
    AiCareerNarrativeResponse,
    AiCareerStrengthsAndInterviewResponse,
    AiMiniReportResponse,
    AiReportRequest,
    InterviewQuestion,
    StarRecord,
    StrengthItem,
)
from app.services._clients.llm_client import LLMClient, WorkloadType
from app.services.report._compute import (
    build_evidences,
    competency_frequency,
    missing_high_tags,
    top_detail_tag_stats,
    top_detail_tags,
)
from app.services.report.exceptions import ReportValidationError

logger = get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parents[2] / "prompts" / "report"

_PROMPT_MINI = (_PROMPTS_DIR / "mini.md").read_text(encoding="utf-8")
_PROMPT_BRANDING = (_PROMPTS_DIR / "branding.md").read_text(encoding="utf-8")
_PROMPT_NARRATIVE = (_PROMPTS_DIR / "narrative.md").read_text(encoding="utf-8")
_PROMPT_STRENGTHS = (_PROMPTS_DIR / "strengths.md").read_text(encoding="utf-8")
_PROMPT_INTERVIEW = (_PROMPTS_DIR / "interview.md").read_text(encoding="utf-8")
_PROMPT_HIGHLIGHTS = (_PROMPTS_DIR / "highlights.md").read_text(encoding="utf-8")

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)
_USER_TRIGGER = "위 지침에 따라 JSON 한 줄을 출력해."

# 한국어 1자 ≈ 1~2 토큰 + JSON 구조 오버헤드 고려 (eval 실측값 기준으로 산정)
_MAX_TOKENS_MINI = 800  # activitySummary 300자 + nextFocusPoint 150자 (실측 618~631)
_MAX_TOKENS_BRANDING = 250  # brandingStatement 60자 + brandingPattern 짧음 (실측 101~113)
_MAX_TOKENS_NARRATIVE = 600  # narrativeSummary 300자 (실측 507~525)
_MAX_TOKENS_STRENGTHS = 700  # strengths 2~3개 x (title 15 + desc 100 + ids) (실측 624)
_MAX_TOKENS_INTERVIEW = 500  # interviewQuestions 2~3개 x (question + ids)
_MAX_TOKENS_HIGHLIGHTS = 600  # experienceHighlights 2~3개 x 80자 (실측 474~490)


# ── 공용 헬퍼 ────────────────────────────────────────────────────────────────


def _extract_text(content: Any) -> str:
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts).strip()


def _strip_code_fence(text: str) -> str:
    m = _CODE_FENCE_RE.match(text)
    return m.group(1).strip() if m else text


def _parse_json(raw: str) -> dict[str, Any]:
    text = _strip_code_fence(raw)
    try:
        payload = orjson.loads(text)
    except orjson.JSONDecodeError as exc:
        raise ReportValidationError(f"JSON 파싱 실패: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReportValidationError("응답이 JSON object 가 아님")
    return payload


def _require_str(
    payload: dict[str, Any],
    key: str,
    max_len: int | None = None,
) -> str:
    val = payload.get(key)
    if not isinstance(val, str) or not val:
        raise ReportValidationError(f"'{key}' 키 누락 또는 빈 문자열")
    if max_len is not None and len(val) > max_len:
        raise ReportValidationError(
            f"'{key}' 길이 초과({len(val)}자 > {max_len}자): \"{val}\" — {max_len}자 이내로 줄여라"
        )
    return val


def _corrective_msg(reason: str) -> str:
    return (
        f"이전 응답이 형식에 맞지 않다. 이유: {reason}. "
        "다시 시도해. 반드시 지침의 JSON 스키마 한 줄만 출력. "
        "코드블록(```)·도입어·추가 키 모두 금지."
    )


async def _call_llm(
    llm: LLMClient,
    model: str,
    system: str,
    max_tokens: int,
    messages: list[dict[str, str]],
) -> str:
    msg = await llm.create_message(
        workload=WorkloadType.REPORT,
        model=model,
        system=system,
        messages=messages,
        max_tokens=max_tokens,
    )
    return _extract_text(msg.content)


async def _call_with_retry(
    llm: LLMClient,
    model: str,
    system: str,
    max_tokens: int,
    parse_fn: Any,
) -> Any:
    """1차 호출 → 실패 시 corrective 메시지로 1회 재시도."""
    first_msg = [{"role": "user", "content": _USER_TRIGGER}]
    first_raw = await _call_llm(llm, model, system, max_tokens, first_msg)
    try:
        return parse_fn(first_raw)
    except ReportValidationError as first_err:
        logger.warning("report.validation_failed", extra={"attempt": 1, "reason": str(first_err)})
        retry_raw = await _call_llm(
            llm,
            model,
            system,
            max_tokens,
            [
                {"role": "user", "content": _USER_TRIGGER},
                {"role": "assistant", "content": first_raw},
                {"role": "user", "content": _corrective_msg(str(first_err))},
            ],
        )
        try:
            return parse_fn(retry_raw)
        except ReportValidationError as retry_err:
            logger.warning(
                "report.validation_failed", extra={"attempt": 2, "reason": str(retry_err)}
            )
            raise


# ── 프롬프트 렌더링 ────────────────────────────────────────────────────────


def _format_records(records: list[StarRecord]) -> str:
    lines: list[str] = []
    for r in records:
        tags = ", ".join(r.detail_tags)
        lines.append(
            f"[id: {r.star_record_id}] 역량: {r.competency} | 태그: {tags}"
            f" | 작성일: {r.completed_at}\n"
            f"S/T: {r.situation_task}\n"
            f"A: {r.action}\n"
            f"R: {r.result}"
        )
    return "\n\n".join(lines)


def _format_scrums(req: AiReportRequest) -> str:
    lines: list[str] = []
    for day in req.scrums_by_date:
        day_lines = [f"[{day.date}]"]
        for scrum in day.scrums:
            ref = (
                f"심화기록 #{scrum.star_record_id}"
                if scrum.star_record_id is not None
                else "심화기록 없음"
            )
            line = f"  - {scrum.project_name} / {scrum.scrum_title} ({ref}): {scrum.content}"
            day_lines.append(line)
        lines.append("\n".join(day_lines))
    return "\n".join(lines)


def _base_vars(req: AiReportRequest) -> dict[str, str]:
    return {
        "nickname": req.nickname,
        "job": JOB_ROLE_LABELS_KO[req.job],
        "period": f"{req.record_period.from_} ~ {req.record_period.to}",
        "totalCount": str(req.total_count),
        "records": _format_records(req.records),
        "scrums": _format_scrums(req),
    }


def _render(template: str, vars: dict[str, str]) -> str:
    token_re = re.compile(r"\{(" + "|".join(re.escape(k) for k in vars) + r")\}")
    return token_re.sub(lambda m: vars[m.group(1)], template)


# ── mini ─────────────────────────────────────────────────────────────────────


def _parse_mini(raw: str) -> tuple[str, str]:
    p = _parse_json(raw)
    activity = _require_str(p, "activitySummary", 300)
    focus = _require_str(p, "nextFocusPoint", 150)
    return activity, focus


async def run_mini(req: AiReportRequest, llm: LLMClient, model: str) -> AiMiniReportResponse:
    missing = missing_high_tags(req.records, req.job)
    vars = _base_vars(req)
    vars["missingHighTags"] = ", ".join(missing) if missing else "없음"
    system = _render(_PROMPT_MINI, vars)
    activity, focus = await _call_with_retry(llm, model, system, _MAX_TOKENS_MINI, _parse_mini)
    logger.info("report.mini.done", extra={"nickname": req.nickname})
    return AiMiniReportResponse(
        activity_summary=activity,
        next_focus_point=focus,
        competency_frequency=competency_frequency(req.records),
        top_detail_tags=top_detail_tags(req.records),
    )


# ── branding ─────────────────────────────────────────────────────────────────


def _parse_branding(raw: str) -> tuple[str, str]:
    p = _parse_json(raw)
    statement = _require_str(p, "brandingStatement", 60)
    pattern = _require_str(p, "brandingPattern")
    return statement, pattern


async def run_branding(
    req: AiReportRequest, llm: LLMClient, model: str
) -> AiCareerBrandingResponse:
    system = _render(_PROMPT_BRANDING, _base_vars(req))
    statement, pattern = await _call_with_retry(
        llm, model, system, _MAX_TOKENS_BRANDING, _parse_branding
    )
    logger.info("report.branding.done", extra={"nickname": req.nickname})
    return AiCareerBrandingResponse(
        branding_statement=statement,
        branding_pattern=pattern,
        top_detail_tags=top_detail_tag_stats(req.records),
    )


# ── narrative ─────────────────────────────────────────────────────────────────


def _parse_narrative(raw: str) -> str:
    p = _parse_json(raw)
    return _require_str(p, "narrativeSummary", 300)


async def run_narrative(
    req: AiReportRequest, llm: LLMClient, model: str
) -> AiCareerNarrativeResponse:
    system = _render(_PROMPT_NARRATIVE, _base_vars(req))
    summary = await _call_with_retry(llm, model, system, _MAX_TOKENS_NARRATIVE, _parse_narrative)
    logger.info("report.narrative.done", extra={"nickname": req.nickname})
    return AiCareerNarrativeResponse(narrative_summary=summary)


# ── strengths-and-interview ───────────────────────────────────────────────────


def _parse_strengths(raw: str, valid_ids: set[int]) -> list[dict[str, Any]]:
    p = _parse_json(raw)
    items = p.get("strengths")
    if not isinstance(items, list) or not (2 <= len(items) <= 3):
        size = len(items) if isinstance(items, list) else "missing"
        raise ReportValidationError(f"strengths 배열 크기 위반: {size}")
    result: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ReportValidationError(f"strengths[{i}] 가 object 아님")
        title = _require_str(item, "title", 15)
        desc = _require_str(item, "description", 100)
        ids = item.get("evidenceIds")
        if not isinstance(ids, list) or not ids:
            raise ReportValidationError(f"strengths[{i}].evidenceIds 누락 또는 빈 배열")
        if not all(isinstance(x, int) for x in ids):
            raise ReportValidationError(f"strengths[{i}].evidenceIds 에 정수 아닌 값 포함")
        bad = [x for x in ids if x not in valid_ids]
        if bad:
            raise ReportValidationError(f"strengths[{i}].evidenceIds 에 유효하지 않은 id: {bad}")
        result.append({"title": title, "description": desc, "evidenceIds": ids})
    return result


def _parse_interview(raw: str, valid_ids: set[int]) -> list[dict[str, Any]]:
    p = _parse_json(raw)
    items = p.get("interviewQuestions")
    if not isinstance(items, list) or not (2 <= len(items) <= 3):
        raise ReportValidationError(
            f"interviewQuestions 배열 크기 위반: "
            f"{len(items) if isinstance(items, list) else 'missing'}"
        )
    result: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ReportValidationError(f"interviewQuestions[{i}] 가 object 아님")
        question = _require_str(item, "question", 100)
        ids = item.get("evidenceIds")
        if not isinstance(ids, list) or not ids:
            raise ReportValidationError(f"interviewQuestions[{i}].evidenceIds 누락 또는 빈 배열")
        if not all(isinstance(x, int) for x in ids):
            raise ReportValidationError(f"interviewQuestions[{i}].evidenceIds 에 정수 아닌 값 포함")
        bad = [x for x in ids if x not in valid_ids]
        if bad:
            raise ReportValidationError(
                f"interviewQuestions[{i}].evidenceIds 에 유효하지 않은 id: {bad}"
            )
        result.append({"question": question, "evidenceIds": ids})
    return result


async def run_strengths_and_interview(
    req: AiReportRequest, llm: LLMClient, model: str
) -> AiCareerStrengthsAndInterviewResponse:
    valid_ids = {r.star_record_id for r in req.records}
    base = _base_vars(req)

    # 1단계: 강점 도출
    system_strengths = _render(_PROMPT_STRENGTHS, base)
    parse_strengths = lambda raw: _parse_strengths(raw, valid_ids)  # noqa: E731
    strengths_data = await _call_with_retry(
        llm, model, system_strengths, _MAX_TOKENS_STRENGTHS, parse_strengths
    )

    # 강점 evidenceIds 전체 수집
    all_evidence_ids: list[int] = []
    for s in strengths_data:
        for eid in s["evidenceIds"]:
            if eid not in all_evidence_ids:
                all_evidence_ids.append(eid)

    evidences_map = {e.id: e for e in build_evidences(req, all_evidence_ids)}

    strengths = [
        StrengthItem(
            title=s["title"],
            description=s["description"],
            evidences=[evidences_map[eid] for eid in s["evidenceIds"] if eid in evidences_map],
        )
        for s in strengths_data
    ]

    # 2단계: 면접 질문 생성 (강점 context + 근거 기록 전달)
    evidence_record_ids = set(all_evidence_ids)
    evidence_records = [r for r in req.records if r.star_record_id in evidence_record_ids]

    strengths_text = "\n".join(
        f"- {s['title']}: {s['description']} (evidenceIds: {s['evidenceIds']})"
        for s in strengths_data
    )
    interview_vars = {
        "nickname": req.nickname,
        "job": JOB_ROLE_LABELS_KO[req.job],
        "strengths": strengths_text,
        "evidenceRecords": _format_records(evidence_records),
    }
    system_interview = _render(_PROMPT_INTERVIEW, interview_vars)
    parse_interview = lambda raw: _parse_interview(raw, evidence_record_ids)  # noqa: E731
    interview_data = await _call_with_retry(
        llm, model, system_interview, _MAX_TOKENS_INTERVIEW, parse_interview
    )

    interview_questions = [
        InterviewQuestion(
            question=q["question"],
            evidences=[evidences_map[eid] for eid in q["evidenceIds"] if eid in evidences_map],
        )
        for q in interview_data
    ]

    logger.info("report.strengths_interview.done", extra={"nickname": req.nickname})
    return AiCareerStrengthsAndInterviewResponse(
        strengths=strengths,
        interview_questions=interview_questions,
    )


# ── highlights ────────────────────────────────────────────────────────────────


def _parse_highlights(raw: str) -> list[str]:
    p = _parse_json(raw)
    items = p.get("experienceHighlights")
    if not isinstance(items, list) or not (2 <= len(items) <= 3):
        raise ReportValidationError(
            f"experienceHighlights 배열 크기 위반: "
            f"{len(items) if isinstance(items, list) else 'missing'}"
        )
    result: list[str] = []
    for i, item in enumerate(items):
        if not isinstance(item, str) or not item:
            raise ReportValidationError(f"experienceHighlights[{i}] 가 문자열 아님")
        if len(item) > 80:
            raise ReportValidationError(f"experienceHighlights[{i}] 길이 초과: {len(item)} > 80")
        result.append(item)
    return result


async def run_highlights(
    req: AiReportRequest, llm: LLMClient, model: str
) -> AiCareerHighlightsResponse:
    system = _render(_PROMPT_HIGHLIGHTS, _base_vars(req))
    highlights = await _call_with_retry(
        llm, model, system, _MAX_TOKENS_HIGHLIGHTS, _parse_highlights
    )
    logger.info("report.highlights.done", extra={"nickname": req.nickname})
    return AiCareerHighlightsResponse(experience_highlights=highlights)
