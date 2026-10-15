"""The CTF 2027 campus tenant keeps its single-job catalog honest."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.zhiye import Ctf2027
from job_crawler.models import Source


class Replay:
    last_evidence = "ctf-list.json"

    def __init__(self, *, wrong_org: bool = False):
        self.wrong_org = wrong_org

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://hr.ctf.com.cn/campus/jobs"

    async def observed(self, needle: str) -> dict[str, Any]:
        return {
            "url": "https://hr.ctf.com.cn/api/Jobad/GetJobAdPageList",
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
        return {
            "Code": 200,
            "Count": 1,
            "Data": [
                {
                    "Id": "ctf-gmt",
                    "JobAdName": "周大福2027届管理培训生",
                    "OrgId": 1 if self.wrong_org else 34100,
                    "Org": None,
                    "CategoryId": "2",
                    "Kind": "全职",
                    "Duty": "零售运营轮岗",
                    "Require": "2027届毕业生",
                    "PostDate": "2026-09-02T11:52:11",
                    "EndTime": "0001-01-01T00:00:00",
                    "LocNames": ["全国"],
                }
            ],
        }


def source() -> Source:
    return Source(
        source_id="COM0219",
        company_id="COM0219",
        company="周大福珠宝集团有限公司",
        url="https://hr.ctf.com.cn/campus/jobs",
    )


async def test_ctf_catalog(now: datetime) -> None:
    result = await Ctf2027(source(), Replay(), now).collect()
    assert not result.coverage_issues()
    assert len(result.jobs) == result.scopes[0].details == 1
    assert result.jobs[0].unit == ""
    assert result.jobs[0].deadline == ""


async def test_ctf_wrong_org_is_incomplete(now: datetime) -> None:
    result = await Ctf2027(source(), Replay(wrong_org=True), now).collect()
    assert result.coverage_issues()
    assert not result.scopes[0].terminal
