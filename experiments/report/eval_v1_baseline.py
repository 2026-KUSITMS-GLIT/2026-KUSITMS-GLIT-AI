"""Report v1_baseline 평가 스크립트 — 5 엔드포인트 실측.

``experiments/report/fixtures/eval_set_v1.jsonl`` 의 케이스를 실제 Anthropic API 로 태우고
포맷 준수 여부 / 응답시간 / 토큰 / 비용을 측정한다.
**service 의 run_*() 을 그대로 호출**하므로 corrective 재시도도 합산된다.

실행:
    uv run python experiments/report/eval_v1_baseline.py

준비:
    .env 의 ``ANTHROPIC_API_KEY`` 가 유효한 실 키여야 한다.

결과:
    - stdout: 엔드포인트별 + 합산 메트릭 + 실제 출력 내용
    - JSON dump: ``experiments/report/results/{timestamp}_{variant}.json``
    - MD upsert: ``experiments/report/{date}_{variant}.md``
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# 프로젝트 루트를 sys.path에 추가 — uv run python으로 직접 실행 시 app 모듈 인식용
sys.path.insert(0, str(Path(__file__).parents[2]))

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.schemas.report import AiReportRequest
from app.services._clients.exceptions import LLMError
from app.services._clients.llm_client import LLMClient
from app.services.report import exceptions as report_exc
from app.services.report import v1_baseline as report_svc

# Anthropic 가격 (USD per million tokens) — claude-haiku-4-5-20251001
_PRICE_INPUT_PER_MTOK = 1.0
_PRICE_OUTPUT_PER_MTOK = 5.0
_USD_TO_KRW = 1400

_HERE = Path(__file__).parent
_FIXTURES = _HERE / "fixtures" / "eval_set_v1.jsonl"
_RESULTS_DIR = _HERE / "results"
_TEMPLATE_PATH = _HERE / "_template.md"


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)

_PLACEHOLDER_KEYS = frozenset({"", "dev-no-api-key", "sk-ant-"})
_CASE_DELAY_SECS = 75  # 케이스 간 대기 — Tier-1 Haiku 50K TPM 초과 방지

import re  # noqa: E402

_METRIC_BLOCK_RE = re.compile(
    r"<!--\s*AUTO:START METRICS\s*-->.*?<!--\s*AUTO:END METRICS\s*-->",
    re.DOTALL,
)

_MINI_ENDPOINTS = ["mini"]
_CAREER_ENDPOINTS = ["branding", "narrative", "strengths_and_interview", "highlights"]


# ── LLM 호출 추적기 ───────────────────────────────────────────────────────────


class _LLMTracker:
    """LLMClient 를 감싸 각 호출의 토큰·지연을 기록한다."""

    def __init__(self, inner: LLMClient) -> None:
        self._inner = inner
        self.calls: list[dict[str, Any]] = []

    async def create_message(self, **kwargs: Any) -> Any:
        start = time.perf_counter()
        msg = await self._inner.create_message(**kwargs)
        latency_ms = int((time.perf_counter() - start) * 1000)
        self.calls.append(
            {
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
                "latency_ms": latency_ms,
            }
        )
        return msg

    # LLMClient 의 나머지 속성 위임
    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    @property
    def workload_semaphores(self) -> Any:
        return self._inner.workload_semaphores  # type: ignore[attr-defined]


# ── 엔드포인트별 실행 ─────────────────────────────────────────────────────────


async def _run_endpoint(
    name: str,
    req: AiReportRequest,
    tracker: _LLMTracker,
    model: str,
) -> dict[str, Any]:
    """단일 엔드포인트를 실행하고 결과 dict 반환."""
    calls_before = len(tracker.calls)
    start = time.perf_counter()
    result_obj: Any = None
    parse_err: str | None = None
    llm_err: str | None = None

    try:
        fn = getattr(report_svc, f"run_{name}")
        result_obj = await fn(req, tracker, model)
    except report_exc.ReportValidationError as e:
        parse_err = str(e)
    except LLMError as e:
        llm_err = f"{type(e).__name__}: {e}"

    latency_ms = int((time.perf_counter() - start) * 1000)
    new_calls = tracker.calls[calls_before:]
    total_in = sum(c["input_tokens"] for c in new_calls)
    total_out = sum(c["output_tokens"] for c in new_calls)
    cost_usd = (
        total_in / 1_000_000 * _PRICE_INPUT_PER_MTOK
        + total_out / 1_000_000 * _PRICE_OUTPUT_PER_MTOK
    )

    return {
        "endpoint": name,
        "ok": result_obj is not None,
        "parse_error": parse_err,
        "llm_error": llm_err,
        "had_corrective": len(new_calls) > (2 if name == "strengths_and_interview" else 1),
        "latency_ms": latency_ms,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cost_usd": cost_usd,
        "output": result_obj.model_dump(by_alias=True) if result_obj else None,
    }


async def _eval_one(inner_llm: LLMClient, model: str, case: dict[str, Any]) -> dict[str, Any]:
    req = AiReportRequest.model_validate(case["input"])
    tracker = _LLMTracker(inner_llm)
    case_type = case.get("type", "career")
    endpoints = _MINI_ENDPOINTS if case_type == "mini" else _CAREER_ENDPOINTS

    endpoint_results: list[dict[str, Any]] = []
    for name in endpoints:
        r = await _run_endpoint(name, req, tracker, model)
        endpoint_results.append(r)

    return {
        "id": case["id"],
        "title": case.get("title", ""),
        "type": case_type,
        "endpoints": endpoint_results,
    }


# ── 출력 ─────────────────────────────────────────────────────────────────────


def _status(ep: dict[str, Any]) -> str:
    if ep["llm_error"]:
        return "LLM_ERR"
    if ep["parse_error"]:
        return "PARSE_ERR"
    return "OK"


def _print_results(case_results: list[dict[str, Any]]) -> None:
    for case in case_results:
        print(f"\n{'=' * 60}")
        print(f"[{case['id']}] ({case.get('type', 'career')}) {case['title']}")
        print(f"{'=' * 60}")

        for ep in case["endpoints"]:
            status = _status(ep)
            corrective = " (corrective)" if ep["had_corrective"] else ""
            print(
                f"\n  [{ep['endpoint']}] {status}{corrective}"
                f"  {ep['latency_ms']}ms"
                f"  tok={ep['input_tokens']}/{ep['output_tokens']}"
                f"  cost=${ep['cost_usd']:.4f}"
            )
            if ep["llm_error"]:
                print(f"    ! {ep['llm_error']}")
            elif ep["parse_error"]:
                print(f"    ! {ep['parse_error']}")
            elif ep["output"]:
                _print_output(ep["endpoint"], ep["output"])

        # 합산
        eps = case["endpoints"]
        total_lat = sum(e["latency_ms"] for e in eps)
        total_in = sum(e["input_tokens"] for e in eps)
        total_out = sum(e["output_tokens"] for e in eps)
        total_cost = sum(e["cost_usd"] for e in eps)
        n_ok = sum(1 for e in eps if e["ok"])
        print(
            f"\n  ── 합산: {n_ok}/{len(eps)} 성공"
            f"  {total_lat}ms  tok={total_in}/{total_out}"
            f"  cost=${total_cost:.4f} (≈{total_cost * _USD_TO_KRW:.1f}원)"
        )
        monthly = total_cost * 1000
        print(f"  ── 월 1,000케이스: ${monthly:.2f} (≈{monthly * _USD_TO_KRW:,.0f}원)")


def _print_output(endpoint: str, output: dict[str, Any]) -> None:
    """엔드포인트별 주요 필드만 요약 출력."""
    if endpoint == "mini":
        act = output.get("activitySummary", "")
        foc = output.get("nextFocusPoint", "")
        print(f"    activitySummary ({len(act)}자): {act[:80]}...")
        print(f"    nextFocusPoint  ({len(foc)}자): {foc}")
    elif endpoint == "branding":
        stmt = output.get("brandingStatement", "")
        pat = output.get("brandingPattern", "")
        print(f"    brandingStatement ({len(stmt)}자): {stmt}")
        print(f"    brandingPattern: {pat[:80]}")
    elif endpoint == "narrative":
        ns = output.get("narrativeSummary", "")
        print(f"    narrativeSummary ({len(ns)}자): {ns[:100]}...")
    elif endpoint == "strengths_and_interview":
        for i, s in enumerate(output.get("strengths", []), 1):
            print(f"    강점{i}: {s.get('title', '')} — {s.get('description', '')[:60]}")
        for i, q in enumerate(output.get("interviewQuestions", []), 1):
            print(f"    질문{i}: {q.get('question', '')[:80]}")
    elif endpoint == "highlights":
        for i, h in enumerate(output.get("experienceHighlights", []), 1):
            print(f"    하이라이트{i} ({len(h)}자): {h}")


# ── 저장 ─────────────────────────────────────────────────────────────────────


def _save_raw(case_results: list[dict[str, Any]], variant: str, model: str, ran_at: str) -> Path:
    _RESULTS_DIR.mkdir(exist_ok=True)
    path = _RESULTS_DIR / f"{ran_at}_{variant}.json"
    path.write_text(
        json.dumps(
            {"variant": variant, "model": model, "ran_at": ran_at, "cases": case_results},
            ensure_ascii=False,
            indent=2,
        )
    )
    return path


def _build_endpoint_subtable(case_results: list[dict[str, Any]], endpoints: list[str]) -> str:
    n = len(case_results)
    agg: dict[str, dict[str, Any]] = {
        ep: {"ok": 0, "lat": [], "in": [], "out": [], "cost": [], "corrective": 0}
        for ep in endpoints
    }
    for case in case_results:
        for ep in case["endpoints"]:
            name = ep["endpoint"]
            if name not in agg:
                continue
            if ep["ok"]:
                agg[name]["ok"] += 1
                agg[name]["lat"].append(ep["latency_ms"])
                agg[name]["in"].append(ep["input_tokens"])
                agg[name]["out"].append(ep["output_tokens"])
                agg[name]["cost"].append(ep["cost_usd"])
            if ep["had_corrective"]:
                agg[name]["corrective"] += 1

    lines = [
        "| 엔드포인트 | 성공 | corrective | latency | 입력tok | 출력tok | 1건 비용 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for ep in endpoints:
        a = agg[ep]
        ok = a["ok"]
        if ok:
            avg_lat = sum(a["lat"]) / ok
            avg_in = sum(a["in"]) / ok
            avg_out = sum(a["out"]) / ok
            avg_cost = sum(a["cost"]) / ok
            cost_str = f"${avg_cost:.4f}"
        else:
            avg_lat = avg_in = avg_out = 0.0
            cost_str = "-"
        lines.append(
            f"| {ep} | {ok}/{n} | {a['corrective']} | {avg_lat:.0f}ms"
            f" | {avg_in:.0f} | {avg_out:.0f} | {cost_str} |"
        )
    return "\n".join(lines)


def _build_endpoint_table(case_results: list[dict[str, Any]]) -> str:
    mini = [c for c in case_results if c.get("type") == "mini"]
    career = [c for c in case_results if c.get("type", "career") == "career"]
    parts = []
    if mini:
        parts.append(f"**Mini** ({len(mini)}케이스)")
        parts.append(_build_endpoint_subtable(mini, _MINI_ENDPOINTS))
    if career:
        parts.append(f"**Career** ({len(career)}케이스)")
        parts.append(_build_endpoint_subtable(career, _CAREER_ENDPOINTS))
    return "\n\n".join(parts)


def _build_case_table(case_results: list[dict[str, Any]]) -> str:
    all_eps = ["mini", "branding", "narrative", "strengths_and_interview", "highlights"]
    lines = [
        "| id | type | " + " | ".join(all_eps) + " |",
        "| --- | --- | " + " | ".join([":---:"] * len(all_eps)) + " |",
    ]
    for case in case_results:
        ep_map = {ep["endpoint"]: _status(ep) for ep in case["endpoints"]}
        case_type = case.get("type", "career")
        cols = " | ".join(ep_map.get(ep, "—") for ep in all_eps)
        lines.append(f"| {case['id']} | {case_type} | {cols} |")
    return "\n".join(lines)


def _upsert_md(
    out_path: Path,
    case_results: list[dict[str, Any]],
    variant: str,
    model: str,
    ran_at: str,
    raw_json_name: str,
) -> str:
    n = len(case_results)
    all_eps = [ep for case in case_results for ep in case["endpoints"]]
    ok_eps = [ep for ep in all_eps if ep["ok"]]
    n_ok_cases = sum(1 for case in case_results if all(ep["ok"] for ep in case["endpoints"]))
    n_parse = sum(1 for ep in all_eps if ep["parse_error"])
    n_llm = sum(1 for ep in all_eps if ep["llm_error"])
    n_corrective = sum(1 for ep in all_eps if ep["had_corrective"])

    total_lat = sum(ep["latency_ms"] for ep in ok_eps) / max(n, 1)
    total_in = sum(ep["input_tokens"] for ep in ok_eps) / max(n, 1)
    total_out = sum(ep["output_tokens"] for ep in ok_eps) / max(n, 1)
    total_cost = sum(ep["cost_usd"] for ep in ok_eps) / max(n, 1)

    ctx = {
        "MODEL": model,
        "VARIANT": variant,
        "RAN_AT": ran_at,
        "DATE": ran_at[:10],
        "N_CASES": str(n),
        "N_OK": str(n_ok_cases),
        "N_PARSE_FAIL": str(n_parse),
        "N_LLM_ERR": str(n_llm),
        "N_CORRECTIVE_TOTAL": str(n_corrective),
        "TOTAL_LATENCY": f"{total_lat:.0f}",
        "TOTAL_INPUT_TOK": f"{total_in:.0f}",
        "TOTAL_OUTPUT_TOK": f"{total_out:.0f}",
        "TOTAL_COST_USD": f"{total_cost:.4f}",
        "TOTAL_COST_KRW": f"{total_cost * _USD_TO_KRW:.1f}",
        "MONTHLY_COST_USD": f"{total_cost * 1000:.2f}",
        "MONTHLY_COST_KRW": f"{total_cost * 1000 * _USD_TO_KRW:,.0f}",
        "RAW_JSON_NAME": raw_json_name,
        "ENDPOINT_TABLE": _build_endpoint_table(case_results),
        "CASE_TABLE": _build_case_table(case_results),
    }

    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = template
    for key, value in ctx.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)

    new_block_match = _METRIC_BLOCK_RE.search(rendered)
    assert new_block_match
    new_block = new_block_match.group(0)

    if not out_path.exists():
        out_path.write_text(rendered, encoding="utf-8")
        return f"created → {_display_path(out_path)}"

    existing = out_path.read_text(encoding="utf-8")
    if _METRIC_BLOCK_RE.search(existing):
        updated = _METRIC_BLOCK_RE.sub(lambda _m: new_block, existing, count=1)
        out_path.write_text(updated, encoding="utf-8")
        return f"updated (인사이트 보존) → {_display_path(out_path)}"

    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    alt = out_path.with_name(f"{out_path.stem}__autorendered_{ts}{out_path.suffix}")
    alt.write_text(rendered, encoding="utf-8")
    return f"conflict. alt 생성 → {_display_path(alt)}"


# ── main ──────────────────────────────────────────────────────────────────────


async def main() -> None:
    configure_logging()
    settings = get_settings()

    if settings.anthropic_api_key in _PLACEHOLDER_KEYS:
        sys.exit("ANTHROPIC_API_KEY 가 비어있거나 placeholder. .env 를 확인하세요.")

    cases = [json.loads(line) for line in _FIXTURES.read_text().splitlines() if line.strip()]
    print(f"Loaded {len(cases)} cases from {_FIXTURES.name}")
    print("Variant: v1_baseline")
    print(f"Model:   {settings.anthropic_model}")

    llm = LLMClient(api_key=settings.anthropic_api_key)
    try:
        case_results: list[dict[str, Any]] = []
        for i, case in enumerate(cases):
            if i > 0:
                print(f"  (rate limit 방지 {_CASE_DELAY_SECS}s 대기...)", flush=True)
                await asyncio.sleep(_CASE_DELAY_SECS)
            print(f"\n[{case['id']}] {case.get('title', '')[:50]} ...", flush=True)
            r = await _eval_one(llm, settings.anthropic_model, case)
            case_results.append(r)
    finally:
        await llm.aclose()

    _print_results(case_results)

    ran_at = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    saved_json = _save_raw(case_results, "v1_baseline", settings.anthropic_model, ran_at)
    print(f"\nRaw saved → {_display_path(saved_json)}")

    md_path = _HERE / f"{ran_at[:10]}_v1_baseline.md"
    status = _upsert_md(
        md_path, case_results, "v1_baseline", settings.anthropic_model, ran_at, saved_json.name
    )
    print(f"MD     → {status}")
    print("→ '관찰' / '결정' 섹션을 채워서 commit 하면 됩니다.")


if __name__ == "__main__":
    asyncio.run(main())
