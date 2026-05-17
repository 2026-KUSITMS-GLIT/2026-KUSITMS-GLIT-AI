# tagging {{VARIANT}} — {{N_CASES}}케이스 실측 ({{DATE}})

<!-- AUTO:START METRICS -->

_생성: `{{RAN_AT}}` · raw: [{{RAW_JSON_NAME}}](results/{{RAW_JSON_NAME}})_

## 메트릭 (자동 채움 — 마커 사이는 eval 재실행 시 덮어쓰임)

### 합산

| 항목 | 값 |
| --- | --- |
| 모델 | `{{MODEL}}` |
| variant | `{{VARIANT}}` |
| 케이스 수 | {{N_CASES}} |
| 평균 일치율 | **{{AVG_SCORE}}%** (exact {{EXACT}} · partial {{PARTIAL}} · none {{NONE}}) |
| 평균 응답시간 | {{AVG_LATENCY}}ms (corrective 포함 합산) |
| 평균 입력 토큰 | {{AVG_INPUT}} (corrective 포함 합산) |
| 평균 출력 토큰 | {{AVG_OUTPUT}} |
| 1건 평균 비용 | ${{AVG_COST_USD}} (≈ {{AVG_COST_KRW}}원) |
| 월 1,000건 비용 | ${{MONTHLY_COST_USD}} (≈ {{MONTHLY_COST_KRW}}원) |
| corrective 발생 | {{N_CORRECTIVE}} / {{N_CASES}} |
| LLM 호출 실패 | {{N_LLM_ERR}} |
| 최종 파싱 실패 (422) | {{N_PARSE_FAIL}} |

### 케이스별

{{CASE_TABLE}}

(굵게: `expected ∩ actual` — 표면 매치)

### 직군별 평균 일치율

{{ROLE_TABLE}}

### 카테고리별 평균 일치율

{{CATEGORY_TABLE}}

<!-- AUTO:END METRICS -->

## 요약

> TODO (1~2줄): 결과 핵심 정리. 평균 일치율 · corrective 발생 여부 · 이전 variant 대비 변화 등.

## 관찰

> TODO: 케이스별 raw response 보면서 인사이트 정리. 자주 유용한 항목:
> - 어느 케이스가 expected 와 크게 달랐는지, 의미적으로는 합리적인지
> - corrective 발생 패턴 (코드블록 / 갯수 / 풀-외 / 기타)
> - 직군 / 카테고리별 편차 해석
> - 일치율 metric 의 표면적 한계 (semantic vs surface)

## 결정

> TODO: 활성 variant 유지/교체 · 후속 PR 권고 · 다음 variant 검토 여부 등.
