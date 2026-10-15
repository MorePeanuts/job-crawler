"""CNOOC group aggregation must agree with the unfiltered campus catalog."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.zhaopin import API, Cnooc2027
from job_crawler.models import Source


class Replay:
    last_evidence = "cnooc-list.json"

    def __init__(self, *, foreign: bool = False):
        self.foreign = foreign
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://cnooc.zhaopin.com/job/index.html"
        assert ready_endpoints == (API,)

    async def observed(self, needle: str) -> dict[str, Any]:
        if needle.endswith("/get-search-aggregation"):
            units = [
                {
                    "name": f"UNIT{index}",
                    "count": 11 if index == 15 else 6,
                    "extend": {
                        "campusOrgName": f"中海油成员企业{index}",
                        "companyInfo": json.dumps(
                            {"campusOrgName": f"中海油成员企业{index}", "rootOrgId": 105147}
                        ),
                    },
                }
                for index in range(16)
            ]
            return {
                "post_data": json.dumps(
                    {
                        "orgNumber": "105147",
                        "jobSource": 2,
                        "facetFields": ["SOU_COMPANY_ID"],
                    }
                ),
                "body": json.dumps({"code": 200, "data": {"itemMap": {"SOU_COMPANY_ID": units}}}),
            }
        assert needle == API
        return {
            "url": API,
            "post_data": json.dumps(
                {
                    "orgNumbers": ["105147"],
                    "jobSource": 2,
                    "pageIndex": 1,
                    "pageSize": 100,
                    "orgDepartmentIds": 10133953,
                    "workRegionIds": "",
                    "jobTypes": "",
                    "priorityMajors": "",
                    "customTags": "",
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert url == API and payload is not None and not detail
        assert payload["orgDepartmentIds"] == []
        page = int(payload["pageIndex"])
        self.pages.append(page)
        start = (page - 1) * 100
        rows = []
        for index in range(start, min(start + 100, 101)):
            unit = min(index // 6, 15)
            rows.append(
                {
                    "company": {
                        "companyId": 105147,
                        "companyNumber": f"UNIT{unit}",
                        "campusOrgName": f"中海油成员企业{unit}",
                        "slaveDisplayOrgName": "其他集团"
                        if self.foreign and index == 100
                        else "中国海油",
                    },
                    "job": {
                        "jobNumber": f"CNOOC{index}",
                        "positionSourceType": 2,
                        "title": f"岗位{index}",
                        "detail": "岗位职责：研发\n任职要求：本科及以上",
                        "cityName": "北京",
                    },
                }
            )
        return {
            "code": 200,
            "data": {
                "jobList": rows,
                "pageInfo": {
                    "pageIndex": page,
                    "pageSize": 100,
                    "totalNum": 101,
                    "totalPage": 2,
                },
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0023",
        company_id="COM0023",
        company="中国海洋石油集团有限公司",
        url="https://cnooc.zhaopin.com/job/index.html",
    )


async def test_cnooc_all_units_and_pages(now: datetime) -> None:
    replay = Replay()
    result = await Cnooc2027(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert result.scopes[0].expected == result.scopes[0].details == 101
    assert len(result.jobs) == 101
    assert result.jobs[-1].unit == "中海油成员企业15"


async def test_cnooc_rejects_foreign_unit(now: datetime) -> None:
    result = await Cnooc2027(source(), Replay(foreign=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 100
