"""LLMClient 수동 테스트 스크립트.

실행:
    uv run python experiments/test_llm_client.py
"""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services._clients.llm_client import LLMClient, WorkloadType

logger = get_logger(__name__)


async def main() -> None:
    configure_logging()
    settings = get_settings()

    client = LLMClient(api_key=settings.anthropic_api_key)

    try:
        logger.info("Claude API 호출 중...")
        response = await client.create_message(
            workload=WorkloadType.TAGGING,
            model=settings.anthropic_model,
            messages=[{"role": "user", "content": "안녕! 한 문장으로 짧게 답해줘."}],
            max_tokens=100,
        )
        logger.info(  # type: ignore[union-attr]
            "응답",
            extra={
                "text": response.content[0].text,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )
        logger.info("LLMClient 정상 동작")
    except Exception as e:
        logger.error("에러 발생", extra={"error_type": type(e).__name__, "error": str(e)})
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
