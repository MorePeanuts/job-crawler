import json
from datetime import datetime
from typing import Any

import pytest

from job_crawler.adapters.huawei import HuaweiGraduate
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture"

    def __init__(self, failure: str = ""):
        self.failure = failure
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        pass

    async def observed(self, needle: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "curPage": 1,
            "pageSize": 10,
            "jobType": "CR",
            "recruitmentType": ["FRESH_GRADUATE"],
        }
        if self.failure == "filter":
            payload["keyword"] = "研发"
        return {
            "url": "https://api.example.test" + needle + "?X-HW-ID=public-site",
            "post_data": json.dumps(payload),
            "public_headers": {
                "x-hw-id": "public-site",
                "x-jalor-tenantalias": "hcm",
                "x-language": "zh_CN",
                "x-referer": "https://career.huawei.com/cn",
                "x-alb-gray": "prod",
            },
        }

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]:
        assert payload is not None
        assert headers == {
            "X-HW-ID": "public-site",
            "X-Jalor-Tenantalias": "hcm",
            "X-Language": "zh_CN",
            "X-Referer": "https://career.huawei.com/cn",
            "X-ALB-Gray": "prod",
        }
        url = url.split("?")[0]
        self.last_evidence = url + json.dumps(payload)
        if url.endswith("getJobPage"):
            page = payload["curPage"]
            self.pages.append(page)
            start = (page - 1) * 10
            if self.failure == "duplicate_page":
                start = 0
            return {
                "status": "SUCCESS",
                "data": {
                    "pageVO": {"curPage": page, "pageSize": 10, "totalRows": 11, "totalPages": 2},
                    "result": [
                        {
                            "advertisementId": i,
                            "jobId": 100 + i,
                            "jobName": f"岗位{i}",
                            "scenarioName": "应届生",
                            "releaseDate": None,
                            "lastUpdateDate": "2026-08-17",
                        }
                        for i in range(start, min(start + 10, 11))
                    ],
                },
            }
        assert detail
        if url.endswith("getRecruitmentPositionDetail"):
            identity = int(payload["advertisementId"])
            return {
                "status": "SUCCESS",
                "data": {
                    "advertisementId": identity,
                    "jobId": 100 + identity,
                    "jobname": f"岗位{identity}",
                    "recruitType": "CR",
                    "scenarioName": "实习生"
                    if self.failure == "intern" and identity == 0
                    else "应届生",
                    "mainBusiness": "请您详见岗位意向中的岗位职责"
                    if identity == 0 or self.failure == "placeholder"
                    else "系统开发",
                    "jobRequire": "本科",
                    "jobCity": "北京",
                    "categoryName": "研发类",
                    "lastUpdateDate": "2026-08-17",
                },
            }
        assert url.endswith("getPositionIntentionList")
        identity = payload["jobId"]
        rows = [
            {
                "jobId": -1 if self.failure == "identity" else identity,
                "positionIntentionId": 1 if self.failure == "duplicate_intent" else i,
                "positionIntention": f"方向{i}",
                "jobResponsibilities": f"职责{i}",
                "jobDemand": f"要求{i}",
                "jobPlaceName": "北京/深圳",
                "deptName": "部门甲,部门乙",
            }
            for i in range(2)
        ]
        return {"status": "SUCCESS", "data": rows if identity == 100 else []}


def source() -> Source:
    return Source(
        source_id="COM0021",
        company_id="COM0021",
        company="华为投资控股有限公司",
        url="https://career.huawei.com/cn/campus-recruitment",
    )


async def test_paginated_parents_expand_all_intentions_without_department_splitting(
    now: datetime,
) -> None:
    replay = Replay()
    result = await HuaweiGraduate(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert len(result.jobs) == 12 and len(result.scopes) == 12
    assert result.scopes[0].unique == result.scopes[0].details == 11
    assert result.jobs[0].source_key == "0:0"
    assert result.jobs[0].title == "岗位0 - 方向0"
    assert result.jobs[0].duties == "职责0"
    assert result.jobs[0].requirements == "要求0"
    assert result.jobs[0].location == "北京/深圳"
    assert all(job.published == "" and job.deadline == "" for job in result.jobs)
    assert all(len(job.evidence) == 3 for job in result.jobs)


@pytest.mark.parametrize(
    "failure", ["filter", "duplicate_page", "duplicate_intent", "identity", "intern", "placeholder"]
)
async def test_invalid_catalog_or_intentions_keep_explicit_gap(now: datetime, failure: str) -> None:
    result = await HuaweiGraduate(source(), Replay(failure), now).collect()
    assert result.coverage_issues()
    assert all("请您详见" not in job.duties for job in result.jobs)
    if failure in {"identity", "duplicate_intent", "intern"}:
        assert len(result.jobs) == 10
