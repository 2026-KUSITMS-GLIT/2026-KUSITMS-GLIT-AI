"""Tagging 도메인 정적 데이터 — 태그 풀 + 5대 역량 카테고리 매핑.

SoT 는 ``.claude/tags.txt`` (26.05.01 수정본). 이 모듈은 LLM 응답이 정해진 풀 안에서만
태그를 골랐는지 검증하기 위한 식별자 집합과, 각 태그가 어느 5대 역량에 속하는지 메타데이터를
노출한다. 직군별 High/Mid/Low 가중치 표는 ``app/prompts/tagging/v1_baseline.md`` 쪽에서
관리한다 (프롬프트 diff 와 분리하기 위함).

``TAGS_BY_CATEGORY`` 를 단일 SoT 로 두고 ``ALL_TAGS`` · ``TAG_TO_CATEGORY`` 는 거기서
파생한다. 두 자료구조가 어긋날 일 없도록 만들기 위함.

태그를 추가/삭제할 때 동기화 대상:
  1. ``.claude/tags.txt`` — 태그풀과 가중치 표
  2. ``app/prompts/tagging/v*.md`` — 프롬프트에 박힌 태그풀·가중치 표
  3. Spring 측 한글 → ENUM 매핑
"""

from __future__ import annotations

from app.schemas.common import PrimaryCategory

TAGS_BY_CATEGORY: dict[PrimaryCategory, frozenset[str]] = {
    PrimaryCategory.DISCOVERY_ANALYSIS: frozenset(
        {
            "#트렌드리서치",
            "#유저리서치",
            "#기술리서치",
            "#데이터해석",
            "#가설검증",
            "#시장분석",
            "#유저인터뷰",
            "#인사이트도출",
            "#도메인학습",
            "#우선순위설정",
            "#사용성평가",
            "#문제정의",
            "#경쟁사례분석",
            "#레퍼런스수집",
        }
    ),
    PrimaryCategory.PLANNING_EXECUTION: frozenset(
        {
            "#기획구조화",
            "#UX설계",
            "#서비스기획",
            "#플로우설계",
            "#기능구현",
            "#프로토타입제작",
            "#API연동",
            "#MVP개발",
            "#지표설계",
            "#시각화작업",
            "#브랜드기획",
            "#컴포넌트구현",
            "#인터랙션설계",
            "#아키텍처설계",
            "#비주얼디자인",
        }
    ),
    PrimaryCategory.COLLABORATION: frozenset(
        {
            "#피드백수용",
            "#의견조율",
            "#팀커뮤니케이션",
            "#직군간협업",
            "#지식공유",
            "#역할분담",
            "#관계자소통",
            "#발표및설득",
            "#산출물전달",
            "#피드백제공",
            "#요구사항정의",
        }
    ),
    PrimaryCategory.PROBLEM_SOLVING: frozenset(
        {
            "#프로세스개선",
            "#문제해결",
            "#구조재설계",
            "#논리보완",
            "#불편개선",
            "#성과개선",
            "#원인분석",
            "#업무자동화",
            "#사용자테스트",
            "#접근성개선",
            "#반복개선",
            "#사용자흐름개선",
            "#검증및테스트",
            "#디버깅",
            "#QA테스트",
        }
    ),
    PrimaryCategory.GROWTH: frozenset(
        {
            "#툴활용",
            "#프로젝트회고",
            "#커리어설계",
            "#팀문화기여",
            "#업무방식개선",
            "#자기객관화",
            "#변화대응",
            "#역량확장",
            "#학습적용",
            "#주도적기여",
            "#성능최적화",
        }
    ),
}
"""5대 역량 카테고리별 태그 집합 — 모듈 내 단일 SoT.

각 태그는 정확히 한 카테고리에 속한다 (현재 풀 기준 중복 없음).
프롬프트 렌더링·분석·디버깅 용도. v1 검증 로직은 카테고리 무관하게
``ALL_TAGS`` 전체를 화이트리스트로 쓴다 (research_ref 결정).
"""


ALL_TAGS: frozenset[str] = frozenset().union(*TAGS_BY_CATEGORY.values())
"""tags.txt 26.05.01 기준 전체 태그 식별자 집합.

LLM 응답의 ``detailTags`` 가 이 집합의 부분집합인지 검사하는 용도.
형식은 ``#태그명`` (해시 prefix · 공백 없음) — tags.txt 원형 그대로.
"""


TAG_TO_CATEGORY: dict[str, PrimaryCategory] = {
    tag: category for category, tags in TAGS_BY_CATEGORY.items() for tag in tags
}
"""태그 → 소속 카테고리 역인덱스. 분석/디버깅 용도."""
