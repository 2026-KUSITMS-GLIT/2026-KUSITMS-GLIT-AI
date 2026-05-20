"""Report 도메인 예외 계층.

LLM 호출 실패(``app.services._clients.exceptions.LLMError`` 하위) 와 분리해서,
**응답 형식·내용 검증 실패** 만 별도로 표현한다. 라우터는 이를 422
(``code: REPORT_GENERATION_FAILED``) 로 매핑한다.
"""

from __future__ import annotations


class ReportError(Exception):
    """Report 도메인 베이스 예외."""


class ReportValidationError(ReportError):
    """LLM 응답이 contract 를 만족하지 못한 경우.

    포함 케이스:
        - JSON 파싱 실패
        - 필수 키 누락 또는 타입 불일치
        - 항목 수가 허용 범위 밖 (예: strengths 2~3개)
        - 허용 evidenceId 외 ID 참조
    """
