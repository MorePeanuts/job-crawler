import json
from datetime import datetime
from math import ceil
from typing import Any

import pytest

from job_crawler.adapters.zto import ZtoCampus
from job_crawler.models import Source


def envelope(data: object) -> dict[str, Any]:
    return {"status": True, "statusCode": "SYS000", "result": data}


def row(key: int) -> dict[str, Any]:
    return {
        "id": key,
        "postNameOut": "物流网络",
        "controlCenterName": "上海中通吉网络技术有限公司",
        "deptNameStr": "中通快递-人力资源中心",
        "workPlaceNameStr": "上海-上海市",
        "workPlaceDetail": "华志路1685号",
        "educationName": "本科",
        "status": 2,
        "duties": "维护网络",
        "qualification": None,
        "gmtModified": 1790145420000,
    }


class Replay:
    last_evidence = "fixture"

    def __init__(self, failure: str = ""):
        self.failure = failure
        self.project = "17"
        self.calls: list[tuple[str, int]] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        if "projectId=" in url:
            self.project = url.split("projectId=")[-1]

    async def observed(self, needle: str) -> dict[str, Any]:
        if "getDictionaryCascade" in needle:
            projects = [
                {"key": "17", "value": "2027校招-总部", "list": None},
                {"key": "18", "value": "2027校招-省区", "list": None},
            ]
            if self.failure == "year":
                projects[1]["value"] = "2028校招-省区"
            return {
                "post_data": json.dumps({"groupName": "school_project", "status": 1}),
                "body": json.dumps(envelope(projects)),
            }
        if "getRecruitmentNews" in needle:
            body = "三、简历投递的起止时间\n即日起至2026年10月31日。"
            if self.failure == "deadline":
                body = "暂无截止"
            return {
                "body": json.dumps(
                    envelope(
                        {
                            "schoolAnnouncements": [
                                {
                                    "name": "2027届校园招聘",
                                    "status": 1,
                                    "recruitingType": 2,
                                    "remark": body,
                                }
                            ]
                        }
                    )
                )
            }
        return {
            "post_data": json.dumps(
                {
                    "schoolObject": ["1"],
                    "postType": 2,
                    "projectId": self.project,
                    "pageSize": 20,
                    "pageNum": 1,
                    "workPlaceIds": [1] if self.failure == "filter" else None,
                }
            )
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None
        if "getPostInfoDetail" in url:
            d = row(int(payload["id"]))
            d["qualification"] = "2027届本科，善于沟通"
            if self.failure == "identity":
                d["controlCenterName"] = "其他公司"
            if self.failure == "missing":
                d["qualification"] = None
            return envelope(d)
        project, page = str(payload["projectId"]), payload["pageNum"]
        self.calls.append((project, page))
        total = 21 if project == "17" else 1
        offset = 0 if project == "17" else 100
        rows = [row(offset + i) for i in range((page - 1) * 20, min(total, page * 20))]
        if self.failure == "duplicate" and page == 2:
            rows = [row(0)]
        if self.failure == "empty" and page == 2:
            rows = []
        if self.failure == "state" and rows:
            rows[0]["status"] = 9
        data = {
            "total": total + (1 if self.failure == "count" and page == 2 else 0),
            "pages": ceil(total / 20),
            "pageNum": page,
            "list": rows,
            "hasNextPage": page * 20 < total,
        }
        response = envelope(data)
        if self.failure == "business":
            response["status"] = False
        return response


def source() -> Source:
    return Source(
        source_id="COM0318",
        company_id="COM0318",
        company="中通快递（开曼）有限公司",
        url="https://hr.zto.com/campus",
    )


async def test_all_projects_full_details_and_deadline(now: datetime) -> None:
    replay = Replay()
    result = await ZtoCampus(source(), replay, now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 22
    assert replay.calls == [("17", 1), ("17", 2), ("18", 1)]
    assert all(j.deadline == "2026-10-31" and not j.published for j in result.jobs)
    assert all(
        j.requirements == "2027届本科，善于沟通" and j.education == "本科" for j in result.jobs
    )


@pytest.mark.parametrize(
    "failure",
    [
        "year",
        "deadline",
        "filter",
        "identity",
        "missing",
        "duplicate",
        "empty",
        "state",
        "count",
        "business",
    ],
)
async def test_changed_catalog_fails(now: datetime, failure: str) -> None:
    result = await ZtoCampus(source(), Replay(failure), now).collect()
    assert result.coverage_issues()
