"""Weichai's list-complete 2027 campus catalog keeps the organization boundary."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.zhiye import WeichaiPower2027
from job_crawler.models import Source


class Replay:
    last_evidence = "weichai-list.json"

    def __init__(self, *, missing_duty: bool = False):
        self.missing_duty = missing_duty
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://weichai.zhiye.com/campus/jobs"

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle.endswith("/GetJobAdPageList")
        return {
            "url": "https://weichai.zhiye.com/api/Jobad/GetJobAdPageList",
            "post_data": json.dumps(
                {
                    "PageIndex": 0,
                    "PageSize": 20,
                    "Category": ["2"],
                    "KeyWords": "",
                    "SpecialType": 0,
                    "PortalId": "",
                    "DisplayFields": ["Category", "Kind", "LocId", "PostDate"],
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None and not detail
        page = int(payload["PageIndex"])
        self.pages.append(page)
        start = page * 20
        return {
            "Code": 200,
            "Count": 25,
            "Data": [
                {
                    "Id": str(index),
                    "JobAdName": f"2027研发岗{index}",
                    "OrgId": 2617191 if index < 5 else 2617150,
                    "Org": None,
                    "CategoryId": "2",
                    "Kind": "全职",
                    **({} if self.missing_duty and index == 24 else {"Duty": "研究动力系统"}),
                    "Require": "2027届本科及以上",
                    "PostDate": "2026-08-31T00:00:00",
                    "EndTime": "0001-01-01T00:00:00",
                    "LocNames": ["山东省·潍坊市"],
                }
                for index in range(start, min(start + 20, 25))
            ],
        }


def source() -> Source:
    return Source(
        source_id="COM0126",
        company_id="COM0126",
        company="潍柴动力股份有限公司",
        url="https://weichai.zhiye.com/campus/jobs",
    )


async def test_weichai_complete_catalog(now: datetime) -> None:
    replay = Replay()
    result = await WeichaiPower2027(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [0, 1]
    assert result.scopes[0].details == 25
    assert result.jobs[0].unit == ""
    assert result.jobs[0].deadline == ""
    assert result.jobs[0].requirements == "2027届本科及以上"


async def test_weichai_missing_duty_is_incomplete(now: datetime) -> None:
    result = await WeichaiPower2027(source(), Replay(missing_duty=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 24
