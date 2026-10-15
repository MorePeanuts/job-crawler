"""Replay China Electronics' full group catalog and campus filtering contract."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.cec import ROOT_ID, CecCampus
from job_crawler.filtering import select
from job_crawler.models import Source


class Replay:
    last_evidence = "cec-replay.json"

    def __init__(self, *, duplicate: bool = False, unknown_unit: bool = False):
        self.duplicate = duplicate
        self.unknown_unit = unknown_unit
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://campus.cec.com.cn/position?positionType=0"
        assert ready_endpoints == ("/student-api/api/position/search",)

    async def observed(self, needle: str) -> dict[str, Any]:
        if needle.endswith(f"/info/{ROOT_ID}"):
            return {
                "body": json.dumps(
                    {
                        "code": "000000",
                        "data": {
                            "orgId": ROOT_ID,
                            "title": "中国电子信息产业集团有限公司",
                        },
                    }
                )
            }
        if needle.endswith("/listOrg"):
            return {
                "body": json.dumps(
                    {
                        "code": "000000",
                        "data": [
                            {
                                "id": ROOT_ID,
                                "name": "中国电子信息产业集团有限公司",
                                "children": [{"id": "2", "name": "成员企业", "children": []}],
                            }
                        ],
                    }
                )
            }
        assert needle.endswith("/position/search")
        return {
            "url": "https://campus.cec.com.cn/student-api/api/position/search",
            "post_data": json.dumps(
                {
                    "page": 1,
                    "size": 10,
                    "name": "",
                    "positionType": "0",
                    "degree": None,
                    "orgId": [],
                }
            ),
        }

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]:
        assert url.endswith("/position/search") and payload is not None and not detail
        page = int(payload["page"])
        self.pages.append(page)
        indexes = range(1, 11) if page == 1 else [1 if self.duplicate else 11]
        rows = [
            {
                "id": str(index),
                "positionNo": f"CEC{index}",
                "positionType": 0,
                "name": f"岗位{index}",
                "org": "未知企业" if self.unknown_unit and index == 11 else "成员企业",
                "workNature": "实习生" if index == 11 else "全职",
                "canDeliver": True,
                "applyable": True,
                "expireFlag": index == 10,
                "jobDescription": "研发工作",
                "jobRequirements": "本科及以上",
                "cityName": "深圳",
                "closeDate": "2026-10-15",
            }
            for index in indexes
        ]
        return {
            "code": "000000",
            "data": {"total": 11, "current": page, "size": 10, "pages": 2, "records": rows},
        }


def source() -> Source:
    return Source(
        source_id="COM0110",
        company_id="COM0110",
        company="中国电子信息产业集团有限公司",
        url="https://campus.cec.com.cn/position?positionType=0",
    )


async def test_cec_all_pages_and_imminent_deadline(now: datetime) -> None:
    replay = Replay()
    result = await CecCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert result.scopes[0].expected == result.scopes[0].details == 11
    assert len(result.jobs) == 11
    assert select(result.jobs[9], "all", now).kind == "include"
    assert select(result.jobs[10], "all", now).reason == "outside_campus_scope"


async def test_cec_duplicate_last_page_is_incomplete(now: datetime) -> None:
    result = await CecCampus(source(), Replay(duplicate=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 10


async def test_cec_unknown_group_unit_is_incomplete(now: datetime) -> None:
    result = await CecCampus(source(), Replay(unknown_unit=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 10
