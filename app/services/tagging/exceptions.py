"""Tagging 도메인 예외 계층.

LLM 호출 실패(``app.services._clients.exceptions.LLMError`` 하위) 와 분리해서,
**응답 형식·내용 검증 실패** 만 별도로 표현한다. 라우터는 이를 422
(``code: TAG_EXTRACTION_FAILED``) 로 매핑한다.
"""

from __future__ import annotations


class TaggingError(Exception):
    """Tagging 도메인 베이스 예외."""


class TaggingValidationError(TaggingError):
    """LLM 응답이 contract 를 만족하지 못한 경우.

    포함 케이스:
        - JSON 파싱 실패
        - ``detailTags`` 키 누락 또는 배열 아님
        - 갯수가 1~3 범위 밖
        - 중복 태그 포함
        - 풀(``ALL_TAGS``) 외 태그 포함
    """
