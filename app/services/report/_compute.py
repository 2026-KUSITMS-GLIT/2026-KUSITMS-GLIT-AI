"""단순 집계 헬퍼 — Python에서 계산, AI 불필요."""

from __future__ import annotations

from collections import Counter

from app.schemas.common import JobRole
from app.schemas.report import (
    AiReportRequest,
    CompetencyCount,
    DetailTagStat,
    EvidenceItem,
    ScrumItem,
    StarRecord,
)
from app.services.tagging.data import TagWeight, WEIGHTS_BY_TAG


def competency_frequency(records: list[StarRecord]) -> list[CompetencyCount]:
    counter = Counter(r.competency for r in records)
    return [CompetencyCount(competency=c, count=n) for c, n in counter.most_common()]


def _sorted_tag_items(counter: Counter, top_n: int) -> list[tuple[str, int]]:
    return sorted(counter.items(), key=lambda x: (-x[1], x[0]))[:top_n]


def top_detail_tags(records: list[StarRecord], top_n: int = 3) -> list[str]:
    counter = Counter(tag for r in records for tag in r.detail_tags)
    return [tag for tag, _ in _sorted_tag_items(counter, top_n)]


def top_detail_tag_stats(records: list[StarRecord], top_n: int = 3) -> list[DetailTagStat]:
    counter = Counter(tag for r in records for tag in r.detail_tags)
    return [DetailTagStat(tag=tag, count=count) for tag, count in _sorted_tag_items(counter, top_n)]


def missing_high_tags(records: list[StarRecord], role: JobRole) -> list[str]:
    from app.schemas.common import PrimaryCategory
    from app.services.tagging.data import TAG_TO_CATEGORY

    freq = Counter(r.competency for r in records)
    weakest = min(PrimaryCategory, key=lambda c: freq.get(c, 0))
    high_in_weakest = {
        t for t, w in WEIGHTS_BY_TAG.items()
        if w.get(role) == TagWeight.HIGH and TAG_TO_CATEGORY.get(t) == weakest
    }
    seen = {tag for r in records for tag in r.detail_tags}
    return sorted(high_in_weakest - seen)


def build_evidences(req: AiReportRequest, record_ids: list[int]) -> list[EvidenceItem]:
    """주어진 starRecordId 목록에 대해 스크럼 정보를 조합한 EvidenceItem 목록 반환."""
    record_to_scrum: dict[int, ScrumItem] = {}
    for day in req.scrums_by_date:
        for scrum in day.scrums:
            if scrum.star_record_id is not None:
                record_to_scrum[scrum.star_record_id] = scrum

    record_map = {r.star_record_id: r for r in req.records}
    evidences: list[EvidenceItem] = []
    for rid in record_ids:
        record = record_map.get(rid)
        if record is None:
            continue
        matched_scrum = record_to_scrum.get(rid)
        evidences.append(
            EvidenceItem(
                id=rid,
                project_name=matched_scrum.project_name if matched_scrum else "",
                scrum_title=matched_scrum.scrum_title if matched_scrum else "",
                created_at=record.completed_at[5:].replace("-", "."),  # "2026-04-09" → "04.09"
            )
        )
    return evidences
