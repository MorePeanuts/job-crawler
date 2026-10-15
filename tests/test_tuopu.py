"""拓普校招标签与智联来源码的租户级约束。"""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.zhaopin import TuopuCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "tuopu-list.json"

    def __init__(self, *, tag: str = "校招", org: str = "拓普集团", job_tag: str = "校招"):
        self.tag = tag
        self.org = org
        self.job_tag = job_tag
        self.payloads: list[dict[str, Any]] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://tuopu.zhaopin.com/school/index.html"

    async def observed(self, needle: str) -> dict[str, Any]:
        return {
            "url": needle,
            "post_data": json.dumps(
                {
                    "orgNumbers": "CZ459148810",
                    "jobSource": 1,
                    "pageIndex": 1,
                    "pageSize": 21,
                    "customTags": self.tag,
                    "orgIds": "",
                    "workRegionIds": "",
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None
        assert payload["customTags"] == "校招" and payload["jobSource"] == 1
        assert payload["workRegionIds"] == payload["orgIds"] == ""
        self.payloads.append(payload)
        return {
            "code": 200,
            "data": {
                "jobList": [
                    {
                        "company": {
                            "companyId": 45914881,
                            "slaveDisplayOrgName": self.org,
                            "campusOrgName": "拓普集团",
                        },
                        "job": {
                            "jobNumber": "CC459148810J40369226512",
                            "positionSourceType": 1,
                            "jobCategories": [self.job_tag],
                            "title": "车辆工程类",
                            "detail": "<p>职位描述：汽车电子技术研发</p><p>基本要求：本科及以上</p>",
                            "url": "https://jobs.zhaopin.com/CC459148810J40369226512.htm",
                        },
                    }
                ],
                "pageInfo": {"pageIndex": 1, "pageSize": 50, "totalNum": 1, "totalPage": 1},
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0454",
        company_id="COM0454",
        company="宁波拓普集团股份有限公司",
        url="https://tuopu.zhaopin.com/school/index.html",
    )


async def test_tuopu_keeps_campus_tag_and_source_code(now: datetime) -> None:
    replay = Replay()
    result = await TuopuCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == result.scopes[0].details == 1
    assert result.jobs[0].published == ""
    assert replay.payloads[0]["customTags"] == "校招"


async def test_tuopu_rejects_non_campus_or_foreign_org(now: datetime) -> None:
    for replay in (Replay(tag=""), Replay(org="别的企业"), Replay(job_tag="社招")):
        result = await TuopuCampus(source(), replay, now).collect()
        assert result.coverage_issues()
