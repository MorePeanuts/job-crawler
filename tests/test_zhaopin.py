import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.zhaopin import Unicom, split_detail
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture"

    def __init__(self, *, repeated: bool = False, changed_count: bool = False):
        self.repeated = repeated
        self.changed_count = changed_count
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://zglt.zhaopin.com/scjobs/index.html"

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle.endswith("/search-job-list")
        return {
            "url": needle,
            "post_data": json.dumps(
                {
                    "orgNumbers": ["105347"],
                    "jobSource": 2,
                    "pageIndex": 1,
                    "pageSize": 11,
                    "orgDepartmentIds": [123],
                    "workRegionIds": "",
                    "jobTypes": "",
                    "priorityMajors": "",
                    "customTags": "",
                    "campusParentDepartmentIds": "",
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None and payload["orgDepartmentIds"] == []
        assert payload["jobSource"] == 2 and payload["orgNumbers"] == ["105347"]
        page = int(payload["pageIndex"])
        self.pages.append(page)
        start = 0 if self.repeated else (page - 1) * 50
        rows = [
            {
                "company": {"companyId": 105347, "campusOrgName": "北京市分公司"},
                "job": {
                    "jobNumber": f"CC{i}",
                    "positionSourceType": 2,
                    "title": f"工程师{i}",
                    "detail": "岗位职责：开发软件\n任职要求：本科及以上",
                    "url": f"https://xiaoyuan.zhaopin.com/job/CC{i}",
                    "deliveryPath": f"https://campus1.zhaopin.com/Resume/CheckIntoApp?pid=CC{i}",
                    "address": "北京",
                    "minEducationName": "本科",
                    "jobTypeName": "软件工程师",
                    "modifiedTime": 1790000000000,
                },
            }
            for i in range(start, min(start + 50, 51))
        ]
        return {
            "code": 200,
            "data": {
                "jobList": rows,
                "pageInfo": {
                    "pageIndex": page,
                    "pageSize": 50,
                    "totalNum": 52 if self.changed_count and page == 2 else 51,
                    "totalPage": 2,
                },
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0069",
        company_id="COM0069",
        company="中国联合网络通信股份有限公司",
        url="https://zglt.zhaopin.com/scjobs/index.html",
    )


async def test_zhaopin_full_unfiltered_catalog(now: datetime) -> None:
    replay = Replay()
    result = await Unicom(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert len(result.jobs) == 51
    assert result.scopes[0].expected == result.scopes[0].details == 51
    assert result.jobs[0].requirements == "本科及以上"
    assert result.jobs[0].published == ""
    assert "modifiedTime" in result.jobs[0].field_sources["published"]


async def test_zhaopin_repeated_page_is_incomplete(now: datetime) -> None:
    result = await Unicom(source(), Replay(repeated=True), now).collect()
    assert result.coverage_issues()
    assert any(issue.code == "duplicate_page" for issue in result.issues)


async def test_zhaopin_total_change_is_incomplete(now: datetime) -> None:
    result = await Unicom(source(), Replay(changed_count=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 50


def test_zhaopin_detail_without_requirements() -> None:
    assert split_detail("负责开发软件") == ("负责开发软件", "")
