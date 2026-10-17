import json
from datetime import datetime
from typing import Any

import pytest

from job_crawler.adapters.isoftstone import ISoftStoneCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "list.json"

    def __init__(self, *, failure: str = "", interns_only: bool = False):
        self.failure = failure
        self.interns_only = interns_only
        self.pages: list[int] = []
        self.details: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        pass

    async def observed(self, needle: str) -> dict[str, Any]:
        payload = {"workCity": "", "jobTypeId": "0", "keyWord": "", "maxcount": 6, "page": 1}
        if self.failure == "filtered":
            payload["workCity"] = "北京"
        return {"url": f"https://career.isoftstone.com{needle}", "post_data": json.dumps(payload)}

    def row(self, identity: int) -> dict[str, Any]:
        return {
            "id": str(identity),
            "name": f"工程师{identity}",
            "hiretype_name": "实习" if self.interns_only or identity == 0 else "全职",
            "describe": "维护软件",
            "publish_date": "2026-10-01 12:00:00",
            "educational_name": "本科",
            "address_detail": "北京市 北京市",
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None
        if detail:
            identity = str(payload["id"])
            self.details.append(identity)
            self.last_evidence = f"detail-{identity}.json"
            row = self.row(int(identity))
            row["jobrequirements"] = "熟悉 Python"
            if self.failure == "mismatch" and identity == "1":
                row["id"] = "wrong"
            return {"success": "true", "data": row}
        page = int(payload["page"])
        self.pages.append(page)
        self.last_evidence = f"list-{page}.json"
        start = (page - 1) * 6
        if self.failure == "duplicate" and page == 2:
            start = 0
        rows = [self.row(i) for i in range(start, min(start + 6, 9))]
        if self.failure == "unknown_type":
            rows[0]["hiretype_name"] = "未知"
        return {
            "count": 9,
            "next": None
            if page == 2 or self.failure == "early_end"
            else "http://www.iyuanzhou.cn/mirecruitment/v1/position/portal/campus/all/?page=2&maxcount=6",
            "results": rows,
        }


def source() -> Source:
    return Source(
        source_id="COM0412",
        company_id="COM0412",
        company="软通动力",
        url="https://career.isoftstone.com/talent/htmls/xiaoyuanzhaopin/index.html",
    )


async def test_full_details_paginate_and_exclude_internships(now: datetime) -> None:
    replay = Replay()
    result = await ISoftStoneCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert replay.details == [str(i) for i in range(1, 9)]
    assert len(result.jobs) == 8
    assert all(job.requirements == "熟悉 Python" for job in result.jobs)
    assert all(job.duties == "维护软件" for job in result.jobs)
    assert all(job.address == "" and job.deadline == "" for job in result.jobs)
    assert all(job.published == "2026-10-01 12:00:00" for job in result.jobs)
    assert result.scopes[0].skipped_out_of_scope == 1
    assert result.jobs[-1].evidence == ["detail-8.json"]


async def test_all_internships_are_complete_but_zero_formal_jobs(now: datetime) -> None:
    replay = Replay(interns_only=True)
    result = await ISoftStoneCampus(source(), replay, now).collect()
    assert not result.coverage_issues() and not result.jobs
    assert result.scopes[0].unique == result.scopes[0].skipped_out_of_scope == 9
    assert replay.details == []


@pytest.mark.parametrize(
    "failure", ["early_end", "duplicate", "filtered", "unknown_type", "mismatch"]
)
async def test_bad_catalog_or_detail_cannot_complete(now: datetime, failure: str) -> None:
    result = await ISoftStoneCampus(source(), Replay(failure=failure), now).collect()
    assert result.coverage_issues()
    if failure == "mismatch":
        assert len(result.jobs) == 7
        assert "1" not in {job.source_key for job in result.jobs}
