import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.boe import BoeCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "boe-page.json"

    def __init__(self, *, duplicate: bool = False, wrong_detail: bool = False):
        self.duplicate = duplicate
        self.wrong_detail = wrong_detail
        self.pages: list[int] = []
        self.details: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://campus.boe.com/custom/xzzw?hideMenu=1"

    async def observed(self, needle: str) -> dict[str, Any]:
        return {
            "url": "https://boe.yuegekeji8.cn/api/Jobad/GetJobAdPageList",
            "post_data": json.dumps(
                {
                    "PageIndex": 0,
                    "PageSize": 10,
                    "Category": [15],
                    "KeyWords": "",
                    "type_code": "1",
                    "ClassificationOne": [],
                    "LocId": [],
                    "PostDate": [],
                    "ywbk": "",
                    "activityGuid": "",
                    "activityJobIds": "",
                }
            ),
        }

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
        credentials: str = "include",
    ) -> dict[str, Any]:
        assert credentials == "omit"
        if payload is not None:
            assert payload["type_code"] == "" and payload["Category"] == [15]
            page = int(payload["PageIndex"])
            self.pages.append(page)
            rows = (
                [
                    {
                        "Id": "one",
                        "JobAdName": "研发工程师",
                        "type": "应届生",
                        "yebk": "集团研发",
                        "LocNames": ["北京市"],
                    },
                    {
                        "Id": "intern",
                        "JobAdName": "实习工程师",
                        "type": "实习生",
                        "yebk": "集团研发",
                        "LocNames": ["北京市"],
                    },
                ]
                if page == 0
                else [
                    {
                        "Id": "one" if self.duplicate else "two",
                        "JobAdName": "博士研究员",
                        "type": "博士生招聘",
                        "yebk": "集团研发",
                        "LocNames": ["上海市"],
                    }
                ]
            )
            return {"code": 1, "data": {"counts": 3, "list": rows}}
        key = url.split("jobAdId=")[1]
        self.details.append(key)
        return {
            "code": 1,
            "data": {
                "res": {
                    "Id": "bad" if self.wrong_detail else key,
                    "JobAdName": "研发工程师" if key == "one" else "博士研究员",
                    "type": "应届生" if key == "one" else "博士生招聘",
                    "yebk": "集团研发",
                    "CategoryId": 15,
                    "Status": 1,
                    "Duty": "负责研发",
                    "RequireNew": "博士学历" if key == "two" else "本科及以上",
                    "PostDate": "2026-10-09 09:25:09",
                    "EndTime": "2222-02-02T00:00:00",
                    "LocNames": ["北京市"] if key == "one" else ["上海市"],
                }
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0137",
        company_id="COM0137",
        company="京东方科技集团股份有限公司",
        url="https://campus.boe.com/custom/xzzw?hideMenu=1",
    )


async def test_boe_unfiltered_projects_exclude_intern(now: datetime) -> None:
    replay = Replay()
    result = await BoeCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [0, 1] and replay.details == ["one", "two"]
    assert len(result.jobs) == 2
    assert result.scopes[0].expected == 3
    assert result.scopes[0].skipped_out_of_scope == 1
    assert result.jobs[0].unit == "集团研发"
    assert result.jobs[0].published == "2026-10-09 09:25:09"
    assert result.jobs[0].deadline == ""


async def test_boe_duplicate_page_is_incomplete(now: datetime) -> None:
    result = await BoeCampus(source(), Replay(duplicate=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 1


async def test_boe_detail_identity_failure_is_incomplete(now: datetime) -> None:
    result = await BoeCampus(source(), Replay(wrong_detail=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 0
