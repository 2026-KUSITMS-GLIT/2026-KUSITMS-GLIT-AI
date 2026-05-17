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
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from app.core.config import get_settings
from app.core.logging import configure_logging
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

_PLACEHOLDER_KEYS = frozenset({"", "dev-no-api-key", "sk-ant-"})


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


def _save_raw(results: list[dict[str, Any]], variant: str, model: str) -> Path:
    _RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    path = _RESULTS_DIR / f"{ts}_{variant}.json"
    path.write_text(
        json.dumps(
            {
                "variant": variant,
                "model": model,
                "ran_at": ts,
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
    saved = _save_raw(results, settings.tagging_variant, settings.anthropic_model)
    print(f"\nRaw saved → {saved.relative_to(Path.cwd())}")
    print("Next: write up experiments/tagging/<date>_<variant>.md (README §실험결과기록)")


if __name__ == "__main__":
    asyncio.run(main())
