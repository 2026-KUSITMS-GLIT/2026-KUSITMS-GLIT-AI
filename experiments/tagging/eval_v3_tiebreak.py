"""Tagging 평가 스크립트 v3 — eval_set_v2 fixture + must/accept 분리 metric.

기존 :mod:`eval_v1_baseline` 의 단일 expected 비교는 표면 일치율 변동성이 컸음
(v1·v2 measurement md 의 §관찰 한계 참고). ``test_case_v2.md`` 가 must (1~2) /
accept (3~5) / source / 직군 모호 플래그로 정리되며 이 한계가 데이터 측에서
풀려, 평가 스크립트도 이에 맞춰 다시 설계.

v1 스크립트 대비 변경점:
1. fixture: ``eval_set_v1.jsonl`` (10) → ``eval_set_v2.jsonl`` (48 케이스).
2. metric:
   - ``expected ∩ actual / expected`` → must 회수율 · accept 회수율 · 풀 외 비율 분리.
   - 풀 외 = actual 중 must/accept 어느 쪽에도 없는 태그 비율.
   - "exact / partial / none" 단일 점수 → must 전체 충족 케이스 카운트로 대체.
3. 그룹: 직군 / 카테고리 / 길이(ST+A+R 합산 글자수 tertile) / 직군 모호 vs 비모호.
4. case table 컬럼 재구성 (must/accept/풀외 카운트 + actual 태그 강조).

실행::

    uv run python experiments/tagging/eval_v3_tiebreak.py

스크립트 이름의 ``v3_tiebreak`` 은 metric 컨벤션 도입 시점 라벨일 뿐, 실제 측정
variant 는 ``settings.tagging_variant`` 를 따른다 — v1_baseline / v2_postscore /
v3_tiebreak 모두 같은 스크립트로 측정한다.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from collections.abc import Callable, Hashable
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
_USD_TO_KRW = 1400

_HERE = Path(__file__).parent
_FIXTURES = _HERE / "fixtures" / "eval_set_v2.jsonl"
_RESULTS_DIR = _HERE / "results"
_TEMPLATE_PATH = _HERE / "_template.md"

_PLACEHOLDER_KEYS = frozenset({"", "dev-no-api-key", "sk-ant-"})

_METRIC_BLOCK_RE = re.compile(
    r"<!--\s*AUTO:START METRICS\s*-->.*?<!--\s*AUTO:END METRICS\s*-->",
    re.DOTALL,
)

_LEN_BUCKETS: tuple[str, str, str] = ("짧음", "중간", "긺")
"""ST+A+R 글자수 tertile 버킷 라벨. 실측 분포에서 동적으로 분할."""


class _LLMTracker:
    """``LLMClient`` 를 감싸 각 호출의 토큰·지연·응답 텍스트를 기록한다 (v1 동일)."""

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


def _recall(actual: list[str], target: list[str]) -> tuple[int, float]:
    """``target ∩ actual`` 갯수와 비율 (target 기준 재현율)."""
    if not target:
        return 0, 0.0
    hit = len(set(target) & set(actual))
    return hit, hit / len(target)


def _oof(actual: list[str], allowed: set[str]) -> tuple[int, float]:
    """actual 중 ``allowed`` (must/accept 합집합) 밖 갯수와 비율."""
    if not actual:
        return 0, 0.0
    out = len(set(actual) - allowed)
    return out, out / len(actual)


def _body_len(req: TaggingRequest) -> int:
    return len(req.situation_task) + len(req.action) + len(req.result)


def _assign_len_buckets(results: list[dict[str, Any]]) -> None:
    """body_len tertile 로 ``len_bucket`` 필드 in-place 설정.

    동일 fixture 라면 매 run 마다 동일한 버킷 분할이 나온다 (body_len 만 의존).
    """
    ordered = sorted(results, key=lambda r: r["body_len"])
    n = len(ordered)
    t1, t2 = n // 3, 2 * n // 3
    for i, r in enumerate(ordered):
        if i < t1:
            r["len_bucket"] = _LEN_BUCKETS[0]
        elif i < t2:
            r["len_bucket"] = _LEN_BUCKETS[1]
        else:
            r["len_bucket"] = _LEN_BUCKETS[2]


async def _eval_one(inner_llm: LLMClient, model: str, case: dict[str, Any]) -> dict[str, Any]:
    """1케이스를 ``tagging.run`` 으로 태우고 must/accept/풀외 metric 집계."""
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
    must = case["must_tags"]
    accept = case["accept_tags"]
    allowed = set(must) | set(accept)
    must_hit, must_recall = _recall(actual, must)
    accept_hit, accept_recall = _recall(actual, accept)
    oof_count, oof_rate = _oof(actual, allowed)

    return {
        "id": case["id"],
        "title": case.get("title", ""),
        "job_role": req.job_role.value,
        "primary_category": req.selected_competency.value,
        "is_ambiguous": bool(case.get("is_ambiguous", False)),
        "body_len": _body_len(req),
        "len_bucket": "",  # _assign_len_buckets 에서 후처리 채움
        "must_tags": must,
        "accept_tags": accept,
        "actual": actual,
        "must_hit": must_hit,
        "must_recall": must_recall,
        "accept_hit": accept_hit,
        "accept_recall": accept_recall,
        "oof_count": oof_count,
        "oof_rate": oof_rate,
        "full_must": must_hit == len(must),
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


def _ok_only(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in results if not r["parse_error"] and not r["llm_error"]]


def _avg(items: list[dict[str, Any]], key: str) -> float:
    if not items:
        return 0.0
    total: float = sum(r[key] for r in items)
    return total / len(items)


def _print_per_case(results: list[dict[str, Any]]) -> None:
    print("\n=== 케이스별 결과 ===")
    for r in results:
        if r["llm_error"]:
            status = "LLM_ERR"
        elif r["parse_error"]:
            status = "PARSE_ERR"
        else:
            status = (
                f"must {r['must_hit']}/{len(r['must_tags'])}  "
                f"accept {r['accept_hit']}/{len(r['accept_tags'])}  "
                f"oof {r['oof_count']}"
            )
        corrective = " (corrective)" if r["had_corrective"] else ""
        amb = " [모호]" if r["is_ambiguous"] else ""
        print(
            f"  [{r['id']}] {r['job_role']:<10} {r['primary_category']:<20} "
            f"{status:<34} {r['total_latency_ms']}ms "
            f"tok={r['input_tokens']}/{r['output_tokens']} cost=${r['cost_usd']:.4f}"
            f"{corrective}{amb}"
        )
        print(f"        must   : {r['must_tags']}")
        print(f"        accept : {r['accept_tags']}")
        if r["llm_error"]:
            print(f"        ! llm error: {r['llm_error']}")
        elif r["parse_error"]:
            print(f"        ! parse err: {r['parse_error']}")
        else:
            print(f"        actual : {r['actual']}")


def _print_summary(results: list[dict[str, Any]]) -> None:
    n = len(results)
    ok = _ok_only(results)
    n_ok = len(ok)
    n_parse = sum(1 for r in results if r["parse_error"])
    n_llm = sum(1 for r in results if r["llm_error"])
    n_corrective = sum(1 for r in results if r["had_corrective"])
    n_full_must = sum(1 for r in ok if r["full_must"])

    print(f"\n=== 합산 (총 {n}건) ===")
    print(f"  파싱 성공 : {n_ok} · 파싱 실패 : {n_parse} · LLM 실패 : {n_llm}")
    print(f"  corrective 발생 : {n_corrective}건")
    if not ok:
        return

    print(
        f"  평균 must 회수율   : {_avg(ok, 'must_recall') * 100:.1f}% "
        f"  (must 전체 충족 {n_full_must}/{n_ok})"
    )
    print(f"  평균 accept 회수율 : {_avg(ok, 'accept_recall') * 100:.1f}%")
    print(f"  평균 풀 외 비율    : {_avg(ok, 'oof_rate') * 100:.1f}%")
    print(f"  평균 응답시간       : {_avg(ok, 'total_latency_ms'):.0f}ms (총 호출 합산 기준)")
    print(f"  평균 입력토큰       : {_avg(ok, 'input_tokens'):.0f}  (corrective 포함 합산)")
    print(f"  평균 출력토큰       : {_avg(ok, 'output_tokens'):.0f}")
    avg_cost = _avg(ok, "cost_usd")
    print(f"  1건 비용           : ${avg_cost:.4f}  (≈ {avg_cost * _USD_TO_KRW:.2f}원)")
    print(
        f"  월 1,000건         : ${avg_cost * 1000:.2f}  (≈ {avg_cost * 1000 * _USD_TO_KRW:.0f}원)"
    )

    amb_ok = [r for r in ok if r["is_ambiguous"]]
    non_amb = [r for r in ok if not r["is_ambiguous"]]
    if amb_ok:
        print(
            f"\n  [직군 모호] {len(amb_ok)}건 must {_avg(amb_ok, 'must_recall') * 100:.1f}% "
            f"  accept {_avg(amb_ok, 'accept_recall') * 100:.1f}% "
            f"  oof {_avg(amb_ok, 'oof_rate') * 100:.1f}%"
        )
        print(
            f"  [비모호 ] {len(non_amb)}건 must {_avg(non_amb, 'must_recall') * 100:.1f}% "
            f"  accept {_avg(non_amb, 'accept_recall') * 100:.1f}% "
            f"  oof {_avg(non_amb, 'oof_rate') * 100:.1f}%"
        )


def _rel(path: Path) -> Path | str:
    try:
        return path.relative_to(Path.cwd())
    except ValueError:
        return str(path)


def _annotate_actual(r: dict[str, Any]) -> str:
    """actual 태그를 ``**must**`` · ``*accept*`` · 평문(풀외) 으로 강조."""
    must_set = set(r["must_tags"])
    accept_set = set(r["accept_tags"])
    parts: list[str] = []
    for t in r["actual"]:
        if t in must_set:
            parts.append(f"**{t}**")
        elif t in accept_set:
            parts.append(f"*{t}*")
        else:
            parts.append(t)
    return "·".join(parts) if parts else "-"


def _build_case_table(results: list[dict[str, Any]]) -> str:
    lines = [
        "| id | 직군 | 카테고리 | 길이 | must | accept | 풀외 | corr | latency"
        " | tok in/out | actual |",
        "| --- | --- | --- | :---: | :---: | :---: | :---: | :---: | ---: | --- | --- |",
    ]
    for r in results:
        if r["llm_error"]:
            mc, ac, oof, actual = "LLM_ERR", "", "", "-"
        elif r["parse_error"]:
            mc, ac, oof, actual = "PARSE_ERR", "", "", "-"
        else:
            mc = f"{r['must_hit']}/{len(r['must_tags'])}"
            ac = f"{r['accept_hit']}/{len(r['accept_tags'])}"
            oof = str(r["oof_count"])
            actual = _annotate_actual(r)
        corrective = "○" if r["had_corrective"] else "×"  # noqa: RUF001
        amb_marker = " ⚠️" if r["is_ambiguous"] else ""
        role = JOB_ROLE_LABELS_KO[JobRole(r["job_role"])]
        cat = PRIMARY_CATEGORY_LABELS_KO[PrimaryCategory(r["primary_category"])]
        lines.append(
            f"| {r['id']}{amb_marker} | {role} | {cat} | {r['len_bucket']} | "
            f"{mc} | {ac} | {oof} | {corrective} | "
            f"{r['total_latency_ms']}ms | {r['input_tokens']} / {r['output_tokens']} | "
            f"{actual} |"
        )
    return "\n".join(lines)


def _build_recall_group_table(
    results: list[dict[str, Any]],
    group_key: str,
    label_fn: Callable[[Any], str],
    *,
    order: list[Hashable] | None = None,
) -> str:
    """그룹별 must/accept/풀외 평균 표.

    ``group_key`` 값으로 버킷 분할, ``label_fn`` 으로 표 라벨 변환.
    ``order`` 가 주어지면 그 순서대로, 아니면 등장 순서 보존 (dict 삽입 순).
    """
    buckets: dict[Any, list[dict[str, Any]]] = {}
    for r in results:
        if r["parse_error"] or r["llm_error"]:
            continue
        buckets.setdefault(r[group_key], []).append(r)
    if not buckets:
        return "_(파싱 성공 케이스 없음)_"

    keys: list[Any] = list(order) if order is not None else list(buckets.keys())
    lines = [
        "| 분류 | 케이스 수 | must | accept | 풀외 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for k in keys:
        items = buckets.get(k, [])
        if not items:
            continue
        m = _avg(items, "must_recall") * 100
        a = _avg(items, "accept_recall") * 100
        o = _avg(items, "oof_rate") * 100
        lines.append(f"| {label_fn(k)} | {len(items)} | {m:.0f}% | {a:.0f}% | {o:.0f}% |")
    return "\n".join(lines)


def _build_ambiguous_table(results: list[dict[str, Any]]) -> str:
    """직군 모호 vs 비모호 분리집계 표."""
    ok = _ok_only(results)
    amb = [r for r in ok if r["is_ambiguous"]]
    non = [r for r in ok if not r["is_ambiguous"]]
    rows: list[str] = []
    for label, items in (("직군 모호", amb), ("비모호", non)):
        if not items:
            continue
        m = _avg(items, "must_recall") * 100
        a = _avg(items, "accept_recall") * 100
        o = _avg(items, "oof_rate") * 100
        ids = ", ".join(r["id"] for r in items[:5])
        if len(items) > 5:
            ids += f", … (+{len(items) - 5})"
        rows.append(f"| {label} | {len(items)} | {ids} | {m:.0f}% | {a:.0f}% | {o:.0f}% |")
    if not rows:
        return "_(파싱 성공 케이스 없음)_"
    return "\n".join(
        [
            "| 분류 | 케이스 수 | 일부 id | must | accept | 풀외 |",
            "| --- | ---: | --- | ---: | ---: | ---: |",
            *rows,
        ]
    )


def _summary_context(
    results: list[dict[str, Any]],
    variant: str,
    model: str,
    ran_at: str,
    raw_json_name: str,
) -> dict[str, str]:
    n = len(results)
    ok = _ok_only(results)
    n_ok = len(ok)
    n_parse = sum(1 for r in results if r["parse_error"])
    n_llm = sum(1 for r in results if r["llm_error"])
    n_corrective = sum(1 for r in results if r["had_corrective"])

    if ok:
        must_recall = _avg(ok, "must_recall") * 100
        accept_recall = _avg(ok, "accept_recall") * 100
        oof_rate = _avg(ok, "oof_rate") * 100
        n_full_must = sum(1 for r in ok if r["full_must"])
        avg_latency = _avg(ok, "total_latency_ms")
        avg_input = _avg(ok, "input_tokens")
        avg_output = _avg(ok, "output_tokens")
        avg_cost = _avg(ok, "cost_usd")
    else:
        must_recall = accept_recall = oof_rate = 0.0
        n_full_must = 0
        avg_latency = avg_input = avg_output = avg_cost = 0.0

    return {
        "MODEL": model,
        "VARIANT": variant,
        "RAN_AT": ran_at,
        "DATE": ran_at[:10],
        "N_CASES": str(n),
        "N_OK": str(n_ok),
        "AVG_MUST_RECALL": f"{must_recall:.1f}",
        "AVG_ACCEPT_RECALL": f"{accept_recall:.1f}",
        "AVG_OOF_RATE": f"{oof_rate:.1f}",
        "N_FULL_MUST": str(n_full_must),
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
        "ROLE_TABLE": _build_recall_group_table(
            results,
            "job_role",
            lambda k: JOB_ROLE_LABELS_KO[JobRole(k)],
            order=[r.value for r in JobRole],
        ),
        "CATEGORY_TABLE": _build_recall_group_table(
            results,
            "primary_category",
            lambda k: PRIMARY_CATEGORY_LABELS_KO[PrimaryCategory(k)],
            order=[r.value for r in PrimaryCategory],
        ),
        "LENGTH_TABLE": _build_recall_group_table(
            results,
            "len_bucket",
            str,
            order=list(_LEN_BUCKETS),
        ),
        "AMBIGUOUS_TABLE": _build_ambiguous_table(results),
    }


def _render_full_md(template: str, ctx: dict[str, str]) -> str:
    """템플릿의 모든 ``{{KEY}}`` 를 ctx 값으로 치환."""
    out = template
    for key, value in ctx.items():
        out = out.replace(f"{{{{{key}}}}}", value)
    return out


def _upsert_md(out_path: Path, ctx: dict[str, str]) -> str:
    """결과 .md upsert. 마커 사이 메트릭 블록만 교체, "관찰/결정" 섹션 보존."""
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
                tag = f"must {r['must_hit']}/{len(r['must_tags'])}  +oof {r['oof_count']}"
            print(f"{tag:>28}  {r['total_latency_ms']}ms")
            results.append(r)
    finally:
        await llm.aclose()

    _assign_len_buckets(results)
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
