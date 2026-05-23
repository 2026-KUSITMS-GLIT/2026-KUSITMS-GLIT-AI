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

from enum import StrEnum

from app.schemas.common import JobRole, PrimaryCategory

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
    PrimaryCategory.REFLECTION_GROWTH: frozenset(
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


# ---------------------------------------------------------------------------
# 직군별 가중치 (tags.txt 26.05.01 표 그대로)
#
# v3_offload_weights 부터 도입 — LLM 프롬프트에는 가중치 표를 박지 않고, LLM 은 본문
# 근거 강한 순으로 5~7개 후보만 뽑아 주면 우리가 이 dict 와 ``tag_score()`` 로 직군별
# 점수를 매겨 상위 3개로 자른다. variant 비교는 v3 service 와 prompts/tagging/v3*.md
# 참고.


class TagWeight(StrEnum):
    """tags.txt 가중치 표의 High / Mid / Low 분류."""

    HIGH = "High"
    MID = "Mid"
    LOW = "Low"


_WEIGHT_SCORE: dict[TagWeight, int] = {
    TagWeight.HIGH: 3,
    TagWeight.MID: 2,
    TagWeight.LOW: 1,
}
"""High/Mid/Low → 정수 점수 매핑. 후처리에서 top-N 정렬에 쓰임."""


# 아래 매트릭스 가독성을 위한 모듈-로컬 별칭. underscore prefix 로 외부 노출 회피.
_H = TagWeight.HIGH
_M = TagWeight.MID
_L = TagWeight.LOW
_P = JobRole.PLANNER  # 기획
_DV = JobRole.DEVELOPER  # 개발
_DS = JobRole.DESIGNER  # 디자인


WEIGHTS_BY_TAG: dict[str, dict[JobRole, TagWeight]] = {
    # 발견·분석
    "#트렌드리서치": {_P: _H, _DV: _M, _DS: _H},
    "#유저리서치": {_P: _H, _DV: _L, _DS: _H},
    "#기술리서치": {_P: _M, _DV: _H, _DS: _M},
    "#데이터해석": {_P: _H, _DV: _H, _DS: _M},
    "#가설검증": {_P: _H, _DV: _H, _DS: _H},
    "#시장분석": {_P: _H, _DV: _L, _DS: _M},
    "#유저인터뷰": {_P: _H, _DV: _L, _DS: _H},
    "#인사이트도출": {_P: _H, _DV: _M, _DS: _H},
    "#도메인학습": {_P: _M, _DV: _H, _DS: _M},
    "#우선순위설정": {_P: _H, _DV: _M, _DS: _M},
    "#사용성평가": {_P: _H, _DV: _L, _DS: _H},
    "#문제정의": {_P: _H, _DV: _M, _DS: _H},
    "#경쟁사례분석": {_P: _H, _DV: _M, _DS: _H},
    "#레퍼런스수집": {_P: _H, _DV: _M, _DS: _H},
    # 기획·실행
    "#기획구조화": {_P: _H, _DV: _L, _DS: _L},
    "#UX설계": {_P: _H, _DV: _L, _DS: _H},
    "#서비스기획": {_P: _H, _DV: _L, _DS: _M},
    "#플로우설계": {_P: _H, _DV: _H, _DS: _M},
    "#기능구현": {_P: _L, _DV: _H, _DS: _L},
    "#프로토타입제작": {_P: _M, _DV: _M, _DS: _H},
    "#API연동": {_P: _L, _DV: _H, _DS: _L},
    "#MVP개발": {_P: _M, _DV: _H, _DS: _L},
    "#지표설계": {_P: _H, _DV: _H, _DS: _M},
    "#시각화작업": {_P: _M, _DV: _M, _DS: _H},
    "#브랜드기획": {_P: _H, _DV: _L, _DS: _H},
    "#컴포넌트구현": {_P: _L, _DV: _H, _DS: _H},
    "#인터랙션설계": {_P: _M, _DV: _M, _DS: _H},
    "#아키텍처설계": {_P: _L, _DV: _H, _DS: _L},
    "#비주얼디자인": {_P: _L, _DV: _L, _DS: _H},
    # 협업·조율
    "#피드백수용": {_P: _H, _DV: _H, _DS: _H},
    "#의견조율": {_P: _H, _DV: _H, _DS: _H},
    "#팀커뮤니케이션": {_P: _H, _DV: _H, _DS: _H},
    "#직군간협업": {_P: _H, _DV: _H, _DS: _H},
    "#지식공유": {_P: _H, _DV: _H, _DS: _H},
    "#역할분담": {_P: _H, _DV: _M, _DS: _M},
    "#관계자소통": {_P: _H, _DV: _M, _DS: _M},
    "#발표및설득": {_P: _H, _DV: _M, _DS: _M},
    "#산출물전달": {_P: _M, _DV: _H, _DS: _H},
    "#피드백제공": {_P: _H, _DV: _H, _DS: _H},
    "#요구사항정의": {_P: _H, _DV: _M, _DS: _M},
    # 문제해결·개선
    "#프로세스개선": {_P: _H, _DV: _H, _DS: _M},
    "#문제해결": {_P: _H, _DV: _H, _DS: _H},
    "#구조재설계": {_P: _H, _DV: _H, _DS: _M},
    "#논리보완": {_P: _H, _DV: _H, _DS: _H},
    "#불편개선": {_P: _H, _DV: _M, _DS: _H},
    "#성과개선": {_P: _H, _DV: _M, _DS: _M},
    "#원인분석": {_P: _H, _DV: _H, _DS: _M},
    "#업무자동화": {_P: _H, _DV: _H, _DS: _L},
    "#사용자테스트": {_P: _H, _DV: _M, _DS: _H},
    "#디버깅": {_P: _L, _DV: _H, _DS: _L},
    "#접근성개선": {_P: _H, _DV: _H, _DS: _H},
    "#반복개선": {_P: _H, _DV: _H, _DS: _H},
    "#사용자흐름개선": {_P: _H, _DV: _M, _DS: _H},
    "#검증및테스트": {_P: _H, _DV: _H, _DS: _M},
    "#QA테스트": {_P: _H, _DV: _H, _DS: _M},
    # 성찰·성장
    "#툴활용": {_P: _M, _DV: _H, _DS: _H},
    "#프로젝트회고": {_P: _H, _DV: _H, _DS: _H},
    "#커리어설계": {_P: _H, _DV: _H, _DS: _H},
    "#팀문화기여": {_P: _H, _DV: _H, _DS: _H},
    "#업무방식개선": {_P: _H, _DV: _H, _DS: _H},
    "#자기객관화": {_P: _H, _DV: _H, _DS: _H},
    "#변화대응": {_P: _H, _DV: _H, _DS: _H},
    "#역량확장": {_P: _H, _DV: _H, _DS: _H},
    "#학습적용": {_P: _H, _DV: _H, _DS: _H},
    "#주도적기여": {_P: _H, _DV: _H, _DS: _H},
    "#성능최적화": {_P: _L, _DV: _H, _DS: _L},
}
"""태그 × 직군 → 가중치 (tags.txt 26.05.01 표 그대로). 총 66 entry."""  # noqa: RUF001


def tag_score(tag: str, role: JobRole) -> int:
    """주어진 직군에서 태그의 가중치 점수 (1~3). 풀에 없거나 매핑 누락은 0.

    후처리 정렬용. 풀 외 태그는 ``_parse_and_validate`` 에서 미리 걸러지지만,
    방어적으로 0 을 반환해 sort 시 자연스럽게 뒤로 밀린다.
    """
    weights = WEIGHTS_BY_TAG.get(tag)
    if weights is None:
        return 0
    w = weights.get(role)
    if w is None:
        return 0
    return _WEIGHT_SCORE[w]
