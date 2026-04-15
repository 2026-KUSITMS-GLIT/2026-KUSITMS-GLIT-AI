# Glit AI Service

Glit 커리어 기록 서비스의 AI 전담 FastAPI 서버입니다.
Spring Boot 메인 백엔드와 **내부 토큰**으로 통신하는 **Stateless** 서비스로 구성했습니다.
즉, DB 접근 없이 매 요청마다 필요한 데이터는 Spring Boot가 바디에 담아서 보내는 형태입니다.
> 관련해 제안사항이 있다면 @김겨레에게 연락 주시면 됩니다.

현재는 스캐폴드 형태의 기본 구조만 구현해둔 상태입니다.

---

## 빠른 시작

### 1. 의존성 설치 — [uv](https://docs.astral.sh/uv/) 사용

```bash
uv sync
```

### 2. 환경변수

```bash
cp .env.example .env
# .env 를 열어 INTERNAL_API_TOKEN 을 랜덤값으로 교체
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. 실행

```bash
uv run uvicorn app.main:app --reload
```

- Swagger UI: <http://localhost:8000/docs>
- Health: <http://localhost:8000/healthz>, <http://localhost:8000/readyz>

---

## 디렉토리 구조

```
app/
├── main.py              # FastAPI 앱 조립 + 라우터 include + 미들웨어 + lifespan
├── api/v1/              # HTTP 레이어 — 얇게 유지 (파싱/검증/예외→HTTP 변환만)
│   └── health.py
├── core/                # 설정, 로깅, 인증
│   ├── config.py        # pydantic-settings 기반 Settings
│   ├── logging.py       # 로깅 초기화
│   └── security.py      # X-Internal-Token 검증
├── schemas/             # Pydantic 요청/응답 모델 (도메인별 파일 분리 부탁드립니다)
├── services/            # 비즈니스 로직 — 외부 SDK 호출, 프롬프트 조립 등
│                        #   도메인별 하위 디렉토리 + 버전별 파일 분리
│                        #   (상세: "프롬프트 / 실험 버전 관리 컨벤션" 참고)
└── prompts/             # 프롬프트 텍스트 (.md) — 코드와 분리하여 diff 리뷰 용이하게
    └── {domain}/        #   ex) tagging/v1_baseline.md, report/v1_baseline.md

experiments/             # 성능 비교·평가 결과 (앱 밖)
├── {domain}/            #   ex) tagging/2026-04-15_v1_vs_v2_vs_v3.md
│   └── fixtures/        #   평가용 고정 샘플 (.jsonl 등)
└── README.md
```

### 레이어 규약

- **api/** 는 얇게.
  - 요청 바디/쿼리 파싱 → services 호출 → 응답 스키마로 반환합니다.
  - `try/except`는 "예외를 HTTP 상태코드로 변환"하는 용도로만 사용합니다.
  - 비즈니스 로직·외부 SDK 호출은 제외하고 작업 부탁드립니다!
- **services/** 에 실제 로직.
  - 순수 async 함수로 작성합니다. FastAPI 타입(`Request`, `Header`)에 의존하지 않습니다.
  - 단위 테스트 가능하도록 설계해주세요!
- **schemas/** 는 Pydantic v2 모델만 사용합니다.
  - 요청/응답 계약 역할을 하며, 기능별로 파일 분리 (`tagging.py`, `reports.py` 등) 해주시면 됩니다.
  - 여러 스키마에서 공유하는 Enum·한글 매핑은 `schemas/common.py`에 모아주시면 됩니다.
- **core/** 는 인프라 공통.
  - 앱 전체가 쓰는 것만 (설정, 로깅, 인증) 담아주시면 되며,
  - 특정 기능 로직은 제외해주세요.

---

## 새 엔드포인트 추가 시

예시: `POST /v1/echo` — 받은 메시지를 그대로 돌려주는 엔드포인트.

1. `app/schemas/echo.py` — 계약 정의
2. `app/services/echo_service.py` — 로직 구현
3. `app/api/v1/echo.py` — 라우터 작업
4. `app/main.py` 에 라우터 등록

---

## 내부 인증 관련 (`X-Internal-Token`)

- Spring Boot가 모든 요청에 `X-Internal-Token: <INTERNAL_API_TOKEN>` 헤더를 붙이도록 합니다.
- 새 라우터는 **반드시** `dependencies=[Depends(require_internal_token)]` 를 붙여 보호합니다.
- 예외: `health`

---

## 설정 추가 (환경변수)

1. `app/core/config.py` 의 `Settings`에 타입 힌트와 기본값을 붙여 필드 추가합니다.
2. `.env.example` 에 같은 키를 주석과 함께 추가합니다 (값은 더미/플레이스홀더).
3. 코드에서는 `get_settings().field_name` 으로 접근하며, 절대 `os.environ` 직접 읽지 ㅏㅂ니다.않도록 ㅎ

---

## AI provider 붙일 경우

1. `pyproject.toml` 에 필요 설정 추가
2. `Settings` 에 필드 추가:
3. `.env.example` 에 `API_KEY=sk-ant-...` 추가
4. `app/services/` 에 클라이언트 역할 파일 추가
5. 기능별 service (`tagging_service.py`, `report_service.py` …)에서 호출.

---

## 프롬프트 / 실험 버전 관리 컨벤션

서비스 특성상, 같은 기능이라도 **여러 프롬프트·전략을 동시에 돌려보고 성능을 비교**할 일이 생길 듯 합니다.
파일과 코드가 뒤섞이지 않도록 아래 규약을 지켜주세요.

### 1. 네이밍 규칙

`{domain}_v{번호}_{전략}.{확장자}`

- **domain**: 기능 이름 (`tagging`, `report`, `summary` …)
- **번호**: `v1`, `v2` … 단조 증가. 한 번 붙은 번호는 재사용하지 않습니다.
- **전략**: 이 버전의 핵심 아이디어를 snake_case 한 단어로.
  - 예) `baseline`, `fewshot`, `cot`, `json_mode`, `short_ctx`, `role_expert`, `self_consistency`

예시
- `tagging_v1_baseline.md` — zero-shot 최초 버전
- `tagging_v2_fewshot.md` — 5-shot 예시 추가
- `tagging_v3_cot.md` — chain-of-thought 유도

> 모델명(`claude-sonnet-4-6` 등)은 파일명에 넣지 말고 **설정(`Settings`)** 에 두어 분리합니다.
> 프롬프트 버전과 모델 선택은 축이 다르기 때문입니다.

### 2. 디렉토리 구조

```
app/
├── prompts/                      # 프롬프트 텍스트 (코드와 분리)
│   ├── tagging/
│   │   ├── v1_baseline.md
│   │   ├── v2_fewshot.md
│   │   └── v3_cot.md
│   └── report/
│       └── v1_baseline.md
└── services/
    └── tagging/
        ├── __init__.py           # 현재 활성 버전을 export
        ├── v1_baseline.py
        ├── v2_fewshot.py
        └── v3_cot.py
```

- 프롬프트 본문은 **반드시 `.md`로 분리** 해주세요.
  코드와 섞여 있으면 "프롬프트만 바뀐 diff"를 리뷰하기 어렵습니다.
- service 쪽도 버전별 파일로 나눠주세요. 한 파일 안에서 `if variant == "v2"` 분기하지 않습니다.

### 3. 활성 버전 스위치

프로덕션에서 실제로 어느 버전을 쓸지는 **환경변수**로 제어합니다.

1. `app/core/config.py` 의 `Settings` 에 필드 추가
   ```python
   tagging_variant: str = "v1_baseline"
   ```
2. `.env.example` 에 주석과 함께 키 추가
   ```
   # tagging 기능의 활성 프롬프트 버전 (app/prompts/tagging/ 하위)
   TAGGING_VARIANT=v1_baseline
   ```
3. `app/services/tagging/__init__.py` 에서 env 값으로 구현체를 선택해 export
4. 실험 브랜치에서 default 값을 함부로 바꾸지 않습니다. 실험 시엔 **본인 `.env`만** 수정합니다.

### 4. 실험 결과 기록

성능 비교 결과는 `experiments/` 디렉토리에 남깁니다. 코드와 구분하기 위해 앱 밖입니다.

```
experiments/
├── tagging/
│   ├── 2026-04-15_v1_vs_v2_vs_v3.md
│   └── fixtures/
│       └── eval_set_v1.jsonl        # 평가용 고정 샘플
└── README.md
```

결과 파일에 최소 아래 네 가지는 포함해주세요.

1. **요약** — 무엇을, 어떤 데이터로 비교했는지 1~2줄
2. **메트릭 표** — 버전 × (정확도 / 지연 / 토큰·비용) 매트릭스
3. **관찰** — 어느 케이스에서 어느 버전이 나았는지 주관 소감
4. **결정** — 프로덕션에 올릴 버전과 사유 (혹은 "결정 보류" + 다음 액션)

### 5. 폐기 정책 (지우지 마세요)

- "이제 안 쓰는" 버전이라도 **바로 지우지 말아주세요**. 다음 실험의 기준선이 됩니다.
- 완전히 버릴 때는 먼저 `experiments/` 의 결과 파일로 **왜 폐기했는지**를 남긴 뒤 삭제합니다.

---

## 로깅

- `app/core/logging.py` 의 `configure_logging()` 이 `lifespan`에서 호출됩니다.
- 사용법: `logger = get_logger(__name__)` → `logger.info("event key=%s", value)`
- 사건 이름은 `domain.action` 컨벤션 (`tagging.done`, `report.failed`) 지켜주세요.


---

## 배포 메모

- 컨테이너에서 실행할 때: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- **prod는 `.env` 파일을 쓰지 않고,** Parameter Store가 환경변수를 직접 주입합니다.
health check는 `/healthz` (liveness), `/readyz` (readiness) 사용하도록 맞춰주세요.