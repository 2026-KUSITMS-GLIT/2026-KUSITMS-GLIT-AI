# report {{VARIANT}} — {{N_CASES}}케이스 실측 ({{DATE}})

<!-- AUTO:START METRICS -->

_생성: `{{RAN_AT}}` · raw: [{{RAW_JSON_NAME}}](results/{{RAW_JSON_NAME}})_

## 메트릭 (자동 채움 — 마커 사이는 eval 재실행 시 덮어쓰임)

### 합산

| 항목 | 값 |
| --- | --- |
| 모델 | `{{MODEL}}` |
| variant | `{{VARIANT}}` |
| 케이스 수 | {{N_CASES}} |
| 포맷 성공 | {{N_OK}} / {{N_CASES}} (파싱 실패 {{N_PARSE_FAIL}} · LLM 실패 {{N_LLM_ERR}}) |
| corrective 발생 | {{N_CORRECTIVE_TOTAL}} (엔드포인트 호출 기준) |
| 전체 응답시간 (1케이스) | {{TOTAL_LATENCY}}ms (5 엔드포인트 합산) |
| 전체 입력 토큰 (1케이스) | {{TOTAL_INPUT_TOK}} |
| 전체 출력 토큰 (1케이스) | {{TOTAL_OUTPUT_TOK}} |
| 1케이스 총 비용 | ${{TOTAL_COST_USD}} (≈ {{TOTAL_COST_KRW}}원) |
| 월 1,000케이스 비용 | ${{MONTHLY_COST_USD}} (≈ {{MONTHLY_COST_KRW}}원) |

### 엔드포인트별

{{ENDPOINT_TABLE}}

### 케이스별 포맷 준수 여부

{{CASE_TABLE}}

<!-- AUTO:END METRICS -->

## 요약

> TODO (1~2줄): 결과 핵심 정리. 포맷 준수율 · corrective 발생 여부 · 비용 등.

## 관찰 (출력 품질 수동 검토)

> TODO: 각 엔드포인트 실제 출력 보면서 인사이트 정리.
> - activitySummary: 서사형인지 나열형인지
> - brandingStatement: 고정 포맷 "OO님은 ... '...'입니다" 준수 여부
> - brandingPattern: 한 줄 패턴인지 장황한지
> - narrativeSummary: 성장 흐름 서술인지 역량 나열인지
> - strengths: "방식 중심" 서술인지 "활동 중심"인지
> - highlights: [상황]+[행동]+[결과] 구조 준수 여부, 추상 문장 여부
> - interviewQuestions: 이 사람 특화 질문인지 일반 질문인지

## 결정

> TODO: 프롬프트 보완 필요 여부 · 다음 variant 검토 여부 등.