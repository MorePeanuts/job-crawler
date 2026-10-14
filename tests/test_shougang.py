"""Replay the official parent-company filter and total-driven pagination."""

from datetime import datetime
from typing import Any

from job_crawler.adapters.shougang import (
    COMPANY,
    ORG_API,
    PAGE_SIZE,
    ShougangCampus,
)
from job_crawler.models import Source


def row(
    index: int, unit: str = "北京首钢建设集团有限公司", *, expired: bool = False
) -> dict[str, Any]:
    return {
        "pk_publishjob": f"p{index}",
        "rmorg": unit,
        "name": f"岗位{index}",
        "professional": "计算机科学与技术",
        "xlyqname": "本科及以上",
        "workplace": "北京市",
        "responsibility": None,
        "description": None,
        "qualification": None,
        "req_speciality": "计算机类" if index == 1 else None,
        "publishdate": "2026-10-13",
        "enddate": "2026-10-01" if expired else "2027-05-31",
    }


class Replay:
    last_evidence = "entry.json"

    def __init__(self) -> None:
        self.rows = [row(i) for i in range(101)]
        self.rows[1] = row(1, COMPANY)
        self.rows[98] = row(98, COMPANY, expired=True)
        self.rows[100] = row(100, COMPANY)
        self.second_total = 101
        self.requests: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://zp.shougang.com.cn/"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError(f"unexpected observed call: {needle}")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is None
        self.requests.append(url)
        self.last_evidence = f"request-{len(self.requests)}.json"
        if url == ORG_API:
            return {"code": "0", "data": [{"pk_org": COMPANY}, {"pk_org": "其他公司"}]}
        page = 2 if "page=2" in url else 1
        return {
            "code": "0",
            "total": self.second_total if page == 2 else 101,
            "data": self.rows[(page - 1) * PAGE_SIZE : page * PAGE_SIZE],
        }


def source() -> Source:
    return Source(
        source_id="COM0134",
        company_id="COM0134",
        company=COMPANY,
        url="https://zp.shougang.com.cn/",
    )


async def test_shougang_pages_and_parent_boundary(now: datetime) -> None:
    replay = Replay()
    result = await ShougangCampus(source(), replay, now).collect()
    assert result.coverage_issues() == []
    assert [
        (s.expected, s.listed, s.details, s.skipped_out_of_scope, s.skipped_expired)
        for s in result.scopes
    ] == [(101, 101, 2, 98, 1)]
    assert [j.source_key for j in result.jobs] == ["p1", "p100"]
    assert all(j.duties == "" and j.published == "2026-10-13" for j in result.jobs)
    assert len(replay.requests) == 3


async def test_shougang_duplicate_page_is_partial(now: datetime) -> None:
    replay = Replay()
    replay.rows[100] = row(1, COMPANY)
    result = await ShougangCampus(source(), replay, now).collect()
    assert result.coverage_issues()
    assert [j.source_key for j in result.jobs] == ["p1"]
    assert any("重复" in issue.message for issue in result.issues)


async def test_shougang_total_change_is_partial(now: datetime) -> None:
    replay = Replay()
    replay.second_total = 102
    result = await ShougangCampus(source(), replay, now).collect()
    assert result.coverage_issues()
    assert [j.source_key for j in result.jobs] == ["p1"]
    assert any("总数" in issue.message for issue in result.issues)
