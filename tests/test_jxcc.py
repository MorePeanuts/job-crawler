"""Jiangxi Copper campus CMS pagination and source-field validation."""

import json
from datetime import datetime
from typing import Any

from test_adapters import source

from job_crawler.adapters.jxcc import LIST_PATH, JxccCampus


def item(number: int) -> dict[str, Any]:
    return {
        "id": number,
        "openDataId": f"ZW{number}",
        "title": f"校园工程师{number}",
        "menuCode": "M000510",
        "single2": "集团本部" if number == 1 else "所属企业",
        "single3": "专业技术",
        "single5": "本科",
        "single8": "江西省_南昌市",
        "single10": f"https://jthr.jxcc.com:8022/recruitPortal/#/positionDetail?id=ZW{number}",
        "content1": "<p>研发工艺</p>",
        "content2": "<p>本科及以上</p>",
        "postTime": "2026-10-08 09:00:04",
        "endDate": "2026-10-28",
    }


class Replay:
    last_evidence = "offline:jxcc"

    def __init__(self, *, duplicate: bool = False, drift: bool = False):
        self.duplicate = duplicate
        self.drift = drift
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://www.jxcc.com/join/xyJoinList.html"

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == LIST_PATH
        return {
            "url": f"https://www.jxcc.com{LIST_PATH}",
            "post_data": json.dumps(
                {
                    "limit": 10,
                    "menuCode": "M000510",
                    "page": 1,
                    "searchCondition": "",
                    "setting": 0,
                    "sign": "",
                    "sort": "",
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert url == f"https://www.jxcc.com{LIST_PATH}" and payload is not None
        page = payload["page"]
        self.pages.append(page)
        rows = (
            [item(n) for n in range(1, 11)]
            if page == 1
            else [item(1 if self.duplicate else 11), item(12)]
        )
        return {
            "content": rows,
            "totalElements": 13 if self.drift and page == 2 else 12,
            "totalPages": 2,
            "number": page - 1,
            "size": 10,
            "numberOfElements": len(rows),
            "last": page == 2,
        }


async def test_jxcc_reads_complete_campus_pages(now: datetime) -> None:
    replay = Replay()
    result = await JxccCampus(source(JxccCampus.host), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert len(result.jobs) == 12
    assert result.jobs[0].unit == "集团本部"
    assert result.jobs[0].duties == "研发工艺"
    assert result.scopes[0].expected == result.scopes[0].details == 12


async def test_jxcc_duplicate_page_is_partial(now: datetime) -> None:
    result = await JxccCampus(source(JxccCampus.host), Replay(duplicate=True), now).collect()
    assert result.coverage_issues()
    assert not result.scopes[0].terminal


async def test_jxcc_count_drift_is_partial(now: datetime) -> None:
    result = await JxccCampus(source(JxccCampus.host), Replay(drift=True), now).collect()
    assert result.coverage_issues()
    assert not result.scopes[0].terminal
