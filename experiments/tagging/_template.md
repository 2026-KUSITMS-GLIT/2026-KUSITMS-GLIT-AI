# tagging {{VARIANT}} — {{N_CASES}}케이스 실측 ({{DATE}})

<!-- AUTO:START METRICS -->

_생성: `{{RAN_AT}}` · raw: [{{RAW_JSON_NAME}}](results/{{RAW_JSON_NAME}})_

## 메트릭 (자동 채움 — 마커 사이는 eval 재실행 시 덮어쓰임)

### 합산

| 항목 | 값 |
| --- | --- |
| 모델 | `{{MODEL}}` |
| variant | `{{VARIANT}}` |
| 케이스 수 | {{N_CASES}} (파싱 성공 {{N_OK}}) |
| 평균 must 회수율 | **{{AVG_MUST_RECALL}}%** (must 전체 충족 {{N_FULL_MUST}}/{{N_OK}}) |
| 평균 accept 회수율 | {{AVG_ACCEPT_RECALL}}% |
| 평균 풀 외 비율 | {{AVG_OOF_RATE}}% |
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

(actual 강조: **must 정답** · *accept 정답* · 일반=풀외. `⚠️` = 직군 모호 케이스)

### 직군별

{{ROLE_TABLE}}

### 카테고리별

{{CATEGORY_TABLE}}

### 길이별 (ST+A+R 합산 글자수 tertile)

{{LENGTH_TABLE}}

### 직군 모호 vs 비모호

{{AMBIGUOUS_TABLE}}

<!-- AUTO:END METRICS -->

## 요약

> TODO (1~2줄): must/accept 회수율 · 풀외율 · 직군 모호 영향 · 이전 variant 대비 변화 핵심 정리.

## 관찰

> TODO: 케이스별 raw response 보면서 인사이트 정리. 유용한 항목:
> - must miss 가 발생한 케이스 패턴 (의미적으로는 가까운 accept 로 대체했는지, 완전히 빗나갔는지)
> - 풀 외 태그가 나온 케이스 — 어떤 태그를 골랐고 왜 합리적인지/아닌지
> - 직군 모호 케이스 (P-PA-04, DS-DA-04) 의 직군 가중치 처리 흐름
> - corrective 발생 패턴 (코드블록 / 갯수 / 풀-외 / 기타)
> - 직군 / 카테고리 / 길이별 편차 해석

## 결정

> TODO: 활성 variant 유지/교체 · 후속 PR 권고 · 다음 variant 검토 여부 등.
