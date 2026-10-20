"""国泰华盛北森 2027 届目录的身份、年份与空日期回放。"""

import json
from datetime import datetime
from typing import Any, cast

from job_crawler.adapters.zhiye import GuotaiHuashengCampus
from job_crawler.models import Source
from job_crawler.transport import Session


class Replay:
    last_evidence = "gths-list.json"

    def __init__(self, *, wrong_year: bool = False) -> None:
        self.wrong_year = wrong_year
        self.pages: list[int] = []

    async def open(self, url: str, **kwargs: object) -> None:
        assert url == "https://gths.zhiye.com/campus/jobs"

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == "/api/Jobad/GetJobAdPageList"
        return {
            "url": "https://gths.zhiye.com/api/Jobad/GetJobAdPageList",
            "post_data": json.dumps(
                {"PageIndex": 0, "PageSize": 20, "Category": ["2"], "KeyWords": "", "PortalId": ""}
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None and not detail
        assert payload["Category"] == ["2"]
        self.pages.append(payload["PageIndex"])
        rows = [
            {
                "Id": str(index),
                "JobAdName": f"{2026 if self.wrong_year and index == 1 else 2027}校招-岗位{index}",
                "CategoryId": "2",
                "Org": None,
                "LocNames": ["江苏省·苏州市"],
                "ClassificationOne": "供应链类",
                "Duty": "开展国际贸易订单管理",
                "Require": "全日制本科及以上学历",
                "PostDate": "0001-01-01T00:00:00",
                "EndTime": "0001-01-01T00:00:00",
            }
            for index in range(2)
        ]
        return {"Code": 200, "Count": 2, "Data": rows}


def adapter(replay: Replay) -> GuotaiHuashengCampus:
    return GuotaiHuashengCampus(
        Source(
            source_id="COM0374",
            company_id="COM0374",
            company="江苏国泰国际集团股份有限公司",
            url="https://gths.zhiye.com/campus/jobs",
        ),
        cast(Session, replay),
        datetime(2026, 10, 20),
    )


async def test_guotai_full_tenant_listing_and_unit_provenance() -> None:
    replay = Replay()
    result = await adapter(replay).collect()
    assert replay.pages == [0]
    assert not result.coverage_issues()
    assert (result.scopes[0].expected, result.scopes[0].unique, result.scopes[0].details) == (
        2,
        2,
        2,
    )
    assert {job.unit for job in result.jobs} == {"江苏国泰华盛实业有限公司"}
    assert all(job.published == job.deadline == "" for job in result.jobs)
    assert all("官方公司身份" in job.field_sources["unit"] for job in result.jobs)


async def test_guotai_wrong_year_is_partial() -> None:
    result = await adapter(Replay(wrong_year=True)).collect()
    assert result.coverage_issues()
    assert not result.jobs
