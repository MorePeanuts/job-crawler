"""Replay the independently verified vivo and Weidian campus tenants."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.zhiye import KkGroup2027, Vivo2027, Weidian2027
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture:campus-list"

    def __init__(self, host: str, count: int):
        self.host = host
        self.count = count
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert self.host in url

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == "/api/Jobad/GetJobAdPageList"
        return {
            "url": f"https://{self.host}{needle}",
            "post_data": json.dumps(
                {
                    "PageIndex": 0,
                    "PageSize": 20,
                    "Category": ["2"],
                    "KeyWords": "",
                    "SpecialType": 0,
                    "PortalId": "",
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None and not detail
        assert payload["Category"] == ["2"]
        page = int(payload["PageIndex"])
        self.pages.append(page)
        rows = []
        for number in range(page * 20, min((page + 1) * 20, self.count)):
            intern = self.host == "hr.weidian.com" and number == 2
            if self.host == "hr-campus.vivo.com":
                title = f"27届秋招工程师{number}"
            elif self.host == "kkguan.zhiye.com":
                title = f"【27技术管培生】工程师{number}"
            else:
                title = f"工程师（2027校招）{number}"
            rows.append(
                {
                    "Id": str(number),
                    "CategoryId": "2",
                    "JobAdName": title,
                    "Kind": "实习" if intern else "全职",
                    "Duty": "研发产品",
                    "Require": "本科及以上",
                    "PostDate": (
                        "0001-01-01T00:00:00"
                        if self.host == "hr-campus.vivo.com"
                        else "2026-09-20T16:42:27"
                    ),
                    "EndTime": "0001-01-01T00:00:00",
                    "LocNames": ["广东省·深圳市"],
                }
            )
        return {"Code": 200, "Count": self.count, "Data": rows}


async def test_vivo_entire_catalog_and_sentinel_dates(now: datetime) -> None:
    source = Source(
        source_id="COM0511",
        company_id="COM0511",
        company="Vivo",
        url="https://hr-campus.vivo.com/campus/jobs",
    )
    replay = Replay("hr-campus.vivo.com", 21)
    result = await Vivo2027(source, replay, now).collect()
    assert replay.pages == [0, 1]
    assert not result.coverage_issues()
    assert len(result.jobs) == 21
    assert result.jobs[0].published == ""
    assert result.jobs[0].deadline == ""
    assert result.jobs[0].unit == "vivo"


async def test_weidian_excludes_listed_internship(now: datetime) -> None:
    source = Source(
        source_id="COM0784",
        company_id="COM0784",
        company="微店",
        url="https://hr.weidian.com/campus/jobs",
    )
    replay = Replay("hr.weidian.com", 3)
    result = await Weidian2027(source, replay, now).collect()
    assert replay.pages == [0]
    assert not result.coverage_issues()
    assert len(result.jobs) == 3
    assert result.jobs[0].published == "2026-09-20T16:42:27"
    assert [job.work_type for job in result.jobs] == ["校招", "校招", "实习"]


async def test_kkgroup_uses_official_tenant_identity_and_27_project(now: datetime) -> None:
    source = Source(
        source_id="COM0575",
        company_id="COM0575",
        company="KK集团",
        url="https://kkguan.zhiye.com/campus/jobs",
    )
    replay = Replay("kkguan.zhiye.com", 9)
    result = await KkGroup2027(source, replay, now).collect()
    assert replay.pages == [0]
    assert not result.coverage_issues()
    assert len(result.jobs) == 9
    assert all(job.unit == "KK集团" for job in result.jobs)
