"""Tagging v1_baseline 평가 스크립트 — 10케이스 실측.

``experiments/tagging/fixtures/eval_set_v1.jsonl`` 의 10케이스를 실제 Anthropic API 로
태우고 일치율 / 응답시간 / 토큰 / 비용을 측정한다. **service 의 ``run()`` 을 그대로 호출**
하므로 corrective 재시도가 발생하면 그 호출도 합산되어 집계된다 (운영과 동일한 흐름).

실행:
    uv run python experiments/tagging/eval_v1_baseline.py

준비:
    .env 의 ``ANTHROPIC_API_KEY`` 가 유효한 실 키여야 한다. 잘못된 키면 LLM_ERR 로 떨어진다.

결과:
    - stdout: 케이스별 + 합산 메트릭
    - JSON dump: ``experiments/tagging/results/{timestamp}_{variant}.json``
        → ``experiments/tagging/<date>_<variant>.md`` 작성 시 참조 (README §실험결과기록)
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.schemas.common import (
    JOB_ROLE_LABELS_KO,
    PRIMARY_CATEGORY_LABELS_KO,
    JobRole,
    PrimaryCategory,
)
from app.schemas.tagging import TaggingRequest, TaggingResponse
from app.services._clients.exceptions import LLMError
from app.services._clients.llm_client import LLMClient
from app.services.tagging import run as tagging_run
from app.services.tagging.exceptions import TaggingValidationError

# Anthropic 가격 (USD per million tokens) — claude-haiku-4-5-20251001
# https://www.anthropic.com/pricing (2026-05 기준)
_PRICE_INPUT_PER_MTOK = 1.0
_PRICE_OUTPUT_PER_MTOK = 5.0
_USD_TO_KRW = 1400  # 대략 환산. 1건/월비용 표시용

_HERE = Path(__file__).parent
_FIXTURES = _HERE / "fixtures" / "eval_set_v1.jsonl"
_RESULTS_DIR = _HERE / "results"
_TEMPLATE_PATH = _HERE / "_template.md"

_PLACEHOLDER_KEYS = frozenset({"", "dev-no-api-key", "sk-ant-"})

# 마커 사이 메트릭 블록만 in-place 교체 (사람이 적은 "관찰/결정" 보존)
_METRIC_BLOCK_RE = re.compile(
    r"<!--\s*AUTO:START METRICS\s*-->.*?<!--\s*AUTO:END METRICS\s*-->",
    re.DOTALL,
)


class _LLMTracker:
    """``LLMClient`` 를 감싸 각 호출의 토큰·지연·응답 텍스트를 기록한다.

    ``v1_baseline.run()`` 이 corrective 재시도 시 LLMClient 를 2번 부르는데, 그 두 호출의
    metric 을 모두 수집해 합산 비용·토큰을 정확히 산출하기 위함이다.
    """

    def __init__(self, inner: LLMClient) -> None:
        self._inner = inner
        self.calls: list[dict[str, Any]] = []

    async def create_message(self, **kwargs: Any) -> Any:
        start = time.perf_counter()
        msg = await self._inner.create_message(**kwargs)
        latency_ms = int((time.perf_counter() - start) * 1000)
        text = "".join(getattr(b, "text", "") for b in msg.content).strip()
        self.calls.append(
            {
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
                "latency_ms": latency_ms,
                "response_text": text,
            }
        )
        return msg


def _load_fixtures(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _match_score(expected: list[str], actual: list[str]) -> float:
    """expected ∩ actual / expected. 0~1. expected 가 비어있으면 0."""
    if not expected:
        return 0.0
    return len(set(expected) & set(actual)) / len(expected)


async def _eval_one(inner_llm: LLMClient, model: str, case: dict[str, Any]) -> dict[str, Any]:
    """1케이스를 service.run() 으로 태우고 metric 집계."""
    req = TaggingRequest.model_validate(case["input"])
    tracker = _LLMTracker(inner_llm)

    response: TaggingResponse | None = None
    parse_err: str | None = None
    llm_err: str | None = None

    start = time.perf_counter()
    try:
        response = await tagging_run(req, cast(LLMClient, tracker), model)
    except TaggingValidationError as e:
        parse_err = str(e)
    except LLMError as e:
        llm_err = f"{type(e).__name__}: {e}"
    total_latency_ms = int((time.perf_counter() - start) * 1000)

    total_in = sum(c["input_tokens"] for c in tracker.calls)
    total_out = sum(c["output_tokens"] for c in tracker.calls)
    cost_usd = (
        total_in / 1_000_000 * _PRICE_INPUT_PER_MTOK
        + total_out / 1_000_000 * _PRICE_OUTPUT_PER_MTOK
    )
    actual = response.detail_tags if response else []

    return {
        "id": case["id"],
        "title": case.get("title", ""),
        "job_role": req.job_role.value,
        "primary_category": req.selected_competency.value,
        "expected": case["expected_tags"],
        "actual": actual,
        "match_score": _match_score(case["expected_tags"], actual),
        "n_llm_calls": len(tracker.calls),
        "had_corrective": len(tracker.calls) > 1,
        "total_latency_ms": total_latency_ms,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cost_usd": cost_usd,
        "parse_error": parse_err,
        "llm_error": llm_err,
        "raw_calls": tracker.calls,
    }


def _print_per_case(results: list[dict[str, Any]]) -> None:
    print("\n=== 케이스별 결과 ===")
    for r in results:
        if r["llm_error"]:
            status = "LLM_ERR"
        elif r["parse_error"]:
            status = "PARSE_ERR"
        else:
            status = f"{int(r['match_score'] * 100)}%"
        corrective = " (corrective)" if r["had_corrective"] else ""
        print(
            f"  [{r['id']}] {r['job_role']:<10} {r['primary_category']:<20} "
            f"{status:<10} {r['total_latency_ms']}ms "
            f"tok={r['input_tokens']}/{r['output_tokens']} cost=${r['cost_usd']:.4f}{corrective}"
        )
        print(f"        expected : {r['expected']}")
        if r["llm_error"]:
            print(f"        ! llm error: {r['llm_error']}")
        elif r["parse_error"]:
            print(f"        ! parse err: {r['parse_error']}")
        else:
            print(f"        actual   : {r['actual']}")


def _print_summary(results: list[dict[str, Any]]) -> None:
    n = len(results)
    ok = [r for r in results if not r["parse_error"] and not r["llm_error"]]
    n_ok = len(ok)
    n_parse = sum(1 for r in results if r["parse_error"])
    n_llm = sum(1 for r in results if r["llm_error"])
    n_corrective = sum(1 for r in results if r["had_corrective"])

    print(f"\n=== 합산 (총 {n}건) ===")
    print(f"  파싱 성공 : {n_ok} · 파싱 실패 : {n_parse} · LLM 실패 : {n_llm}")
    print(f"  corrective 발생 : {n_corrective}건")
    if not ok:
        return

    avg_score = sum(r["match_score"] for r in ok) / n_ok
    exact = sum(1 for r in ok if r["match_score"] >= 1.0)
    partial = sum(1 for r in ok if 0 < r["match_score"] < 1.0)
    none_ = sum(1 for r in ok if r["match_score"] == 0)
    avg_latency = sum(r["total_latency_ms"] for r in ok) / n_ok
    avg_input = sum(r["input_tokens"] for r in ok) / n_ok
    avg_output = sum(r["output_tokens"] for r in ok) / n_ok
    avg_cost = sum(r["cost_usd"] for r in ok) / n_ok

    breakdown = f"exact {exact} · partial {partial} · none {none_}"
    print(f"  평균 일치율   : {avg_score * 100:.1f}%  ({breakdown})")
    print(f"  평균 응답시간 : {avg_latency:.0f}ms (총 호출 합산 기준)")
    print(f"  평균 입력토큰 : {avg_input:.0f}  (corrective 포함 합산)")
    print(f"  평균 출력토큰 : {avg_output:.0f}")
    print(f"  1건 비용     : ${avg_cost:.4f}  (≈ {avg_cost * _USD_TO_KRW:.2f}원)")
    print(f"  월 1,000건   : ${avg_cost * 1000:.2f}  (≈ {avg_cost * 1000 * _USD_TO_KRW:.0f}원)")


def _rel(path: Path) -> Path | str:
    """cwd 안이면 relative, 밖이면 absolute — 표시 전용 (tmpdir dry-run 호환)."""
    try:
        return path.relative_to(Path.cwd())
    except ValueError:
        return str(path)


def _bold_overlap(tags: list[str], overlap: set[str]) -> str:
    """expected/actual 표시용 — 교집합 태그만 ``**bold**``."""
    return "·".join(f"**{t}**" if t in overlap else t for t in tags)


def _build_case_table(results: list[dict[str, Any]]) -> str:
    """케이스별 markdown 표 (헤더 포함)."""
    lines = [
        "| id | 직군 | 카테고리 | 일치율 | corrective | latency | tok in/out | expected | actual |",
        "| --- | --- | --- | ---: | :---: | ---: | --- | --- | --- |",
    ]
    for r in results:
        if r["llm_error"]:
            score = "LLM_ERR"
        elif r["parse_error"]:
            score = "PARSE_ERR"
        else:
            score = f"{int(r['match_score'] * 100)}%"
        corrective = "○" if r["had_corrective"] else "×"  # noqa: RUF001
        role = JOB_ROLE_LABELS_KO[JobRole(r["job_role"])]
        cat = PRIMARY_CATEGORY_LABELS_KO[PrimaryCategory(r["primary_category"])]
        overlap = set(r["expected"]) & set(r["actual"])
        exp = _bold_overlap(r["expected"], overlap)
        act = _bold_overlap(r["actual"], overlap) if r["actual"] else "-"
        lines.append(
            f"| {r['id']} | {role} | {cat} | {score} | {corrective} | "
            f"{r['total_latency_ms']}ms | {r['input_tokens']} / {r['output_tokens']} | "
            f"{exp} | {act} |"
        )
    return "\n".join(lines)


def _build_group_table(
    results: list[dict[str, Any]],
    group_key: str,
    label_map: dict[Any, str],
    enum_cls: type[Any],
) -> str:
    """직군/카테고리 등 그룹별 평균 일치율 표."""
    buckets: dict[str, list[float]] = {}
    case_ids: dict[str, list[str]] = {}
    for r in results:
        if r["parse_error"] or r["llm_error"]:
            continue
        k = r[group_key]
        buckets.setdefault(k, []).append(r["match_score"])
        case_ids.setdefault(k, []).append(r["id"])
    if not buckets:
        return "_(파싱 성공 케이스 없음)_"
    lines = ["| 분류 | 케이스 | 평균 |", "| --- | --- | ---: |"]
    for k, scores in buckets.items():
        label = label_map.get(enum_cls(k), k)
        avg = sum(scores) / len(scores) * 100
        ids = ", ".join(case_ids[k])
        lines.append(f"| {label} | {ids} | {avg:.0f}% |")
    return "\n".join(lines)


def _summary_context(
    results: list[dict[str, Any]],
    variant: str,
    model: str,
    ran_at: str,
    raw_json_name: str,
) -> dict[str, str]:
    """템플릿 placeholder → 값 매핑 dict."""
    n = len(results)
    ok = [r for r in results if not r["parse_error"] and not r["llm_error"]]
    n_ok = len(ok)
    n_parse = sum(1 for r in results if r["parse_error"])
    n_llm = sum(1 for r in results if r["llm_error"])
    n_corrective = sum(1 for r in results if r["had_corrective"])

    if ok:
        avg_score = sum(r["match_score"] for r in ok) / n_ok
        exact = sum(1 for r in ok if r["match_score"] >= 1.0)
        partial = sum(1 for r in ok if 0 < r["match_score"] < 1.0)
        none_ = sum(1 for r in ok if r["match_score"] == 0)
        avg_latency = sum(r["total_latency_ms"] for r in ok) / n_ok
        avg_input = sum(r["input_tokens"] for r in ok) / n_ok
        avg_output = sum(r["output_tokens"] for r in ok) / n_ok
        avg_cost = sum(r["cost_usd"] for r in ok) / n_ok
    else:
        avg_score = exact = partial = none_ = 0
        avg_latency = avg_input = avg_output = avg_cost = 0.0

    return {
        "MODEL": model,
        "VARIANT": variant,
        "RAN_AT": ran_at,
        "DATE": ran_at[:10],
        "N_CASES": str(n),
        "AVG_SCORE": f"{avg_score * 100:.1f}",
        "EXACT": str(exact),
        "PARTIAL": str(partial),
        "NONE": str(none_),
        "AVG_LATENCY": f"{avg_latency:,.0f}",
        "AVG_INPUT": f"{avg_input:,.0f}",
        "AVG_OUTPUT": f"{avg_output:,.0f}",
        "AVG_COST_USD": f"{avg_cost:.4f}",
        "AVG_COST_KRW": f"{avg_cost * _USD_TO_KRW:.1f}",
        "MONTHLY_COST_USD": f"{avg_cost * 1000:.2f}",
        "MONTHLY_COST_KRW": f"{avg_cost * 1000 * _USD_TO_KRW:,.0f}",
        "N_CORRECTIVE": str(n_corrective),
        "N_LLM_ERR": str(n_llm),
        "N_PARSE_FAIL": str(n_parse),
        "RAW_JSON_NAME": raw_json_name,
        "CASE_TABLE": _build_case_table(results),
        "ROLE_TABLE": _build_group_table(results, "job_role", JOB_ROLE_LABELS_KO, JobRole),
        "CATEGORY_TABLE": _build_group_table(
            results, "primary_category", PRIMARY_CATEGORY_LABELS_KO, PrimaryCategory
        ),
    }


def _render_full_md(template: str, ctx: dict[str, str]) -> str:
    """템플릿의 모든 ``{{KEY}}`` 를 ctx 값으로 치환."""
    out = template
    for key, value in ctx.items():
        out = out.replace(f"{{{{{key}}}}}", value)
    return out


def _upsert_md(out_path: Path, ctx: dict[str, str]) -> str:
    """결과 .md upsert.

    - 마커 사이 메트릭 블록만 in-place 교체하여 사람이 적은 "관찰/결정" 섹션을 보존한다.
    - 파일이 없으면 ``_template.md`` 기반으로 새로 작성한다.
    - 파일은 있지만 마커가 없으면 (옛 수동 작성 .md) 충돌 회피로 ``_<timestamp>`` suffix 의
      alt 파일을 새로 만들고, 기존 파일은 건드리지 않는다.

    Returns:
        사용자에게 보여줄 상태 문자열.
    """
    rendered = _render_full_md(_TEMPLATE_PATH.read_text(encoding="utf-8"), ctx)
    new_block_match = _METRIC_BLOCK_RE.search(rendered)
    assert new_block_match, "_template.md 에 AUTO:START/END METRICS 마커가 있어야 한다"
    new_block = new_block_match.group(0)

    if not out_path.exists():
        out_path.write_text(rendered, encoding="utf-8")
        return f"created → {_rel(out_path)}"

    existing = out_path.read_text(encoding="utf-8")
    if _METRIC_BLOCK_RE.search(existing):
        updated = _METRIC_BLOCK_RE.sub(lambda _m: new_block, existing, count=1)
        out_path.write_text(updated, encoding="utf-8")
        return f"updated (인사이트 보존) → {_rel(out_path)}"

    # 기존 파일에 마커가 없음 — 옛 수동 작성. 건드리지 않고 alt 생성.
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    alt = out_path.with_name(f"{out_path.stem}__autorendered_{ts}{out_path.suffix}")
    alt.write_text(rendered, encoding="utf-8")
    return f"conflict (기존 파일에 마커 없음, 건드리지 않음). alt 생성 → {_rel(alt)}"


def _save_raw(results: list[dict[str, Any]], variant: str, model: str, ran_at: str) -> Path:
    _RESULTS_DIR.mkdir(exist_ok=True)
    path = _RESULTS_DIR / f"{ran_at}_{variant}.json"
    path.write_text(
        json.dumps(
            {
                "variant": variant,
                "model": model,
                "ran_at": ran_at,
                "n_cases": len(results),
                "cases": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return path


async def main() -> None:
    configure_logging()
    settings = get_settings()

    if settings.anthropic_api_key in _PLACEHOLDER_KEYS:
        sys.exit("ANTHROPIC_API_KEY 가 비어있거나 placeholder. .env 를 확인하세요.")

    cases = _load_fixtures(_FIXTURES)
    print(f"Loaded {len(cases)} cases from {_FIXTURES.name}")
    print(f"Variant: {settings.tagging_variant}")
    print(f"Model:   {settings.anthropic_model}")
    print()

    llm = LLMClient(api_key=settings.anthropic_api_key)
    try:
        results: list[dict[str, Any]] = []
        for case in cases:
            short = (case.get("title") or "")[:40]
            print(f"  [{case['id']}] {short}...", flush=True, end=" ")
            r = await _eval_one(llm, settings.anthropic_model, case)
            if r["llm_error"]:
                tag = "LLM_ERR"
            elif r["parse_error"]:
                tag = "PARSE_ERR"
            else:
                tag = f"{int(r['match_score'] * 100)}%"
            print(f"{tag:>10}  {r['total_latency_ms']}ms")
            results.append(r)
    finally:
        await llm.aclose()

    _print_per_case(results)
    _print_summary(results)

    ran_at = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    saved_json = _save_raw(results, settings.tagging_variant, settings.anthropic_model, ran_at)
    print(f"\nRaw saved → {saved_json.relative_to(Path.cwd())}")

    md_path = _HERE / f"{ran_at[:10]}_{settings.tagging_variant}.md"
    ctx = _summary_context(
        results=results,
        variant=settings.tagging_variant,
        model=settings.anthropic_model,
        ran_at=ran_at,
        raw_json_name=saved_json.name,
    )
    status = _upsert_md(md_path, ctx)
    print(f"MD     → {status}")
    print("→ '관찰' / '결정' 섹션을 채워서 commit 하면 README §실험결과기록 컨벤션 충족.")


if __name__ == "__main__":
    asyncio.run(main())
