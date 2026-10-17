import json
from datetime import datetime
from typing import Any

import pytest
from test_zhiye import Replay

from job_crawler.adapters.shenergy import ShenergyListedCampus
from job_crawler.models import Source


class ShenergyReplay(Replay):
    def __init__(self, *, failure: str = ""):
        super().__init__(count=21)
        self.failure = failure

    async def observed(self, needle: str) -> dict[str, Any]:
        if "GetJobAdCustomTypeList" in needle:
            return {
                "url": "https://shenergy.zhiye.com/api/OpenCustomization/GetJobAdCustomTypeList"
            }
        response = await super().observed(needle)
        response["url"] = response["url"].replace("xiangyu", "shenergy")
        return response

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        if "GetJobAdCustomTypeList" in url:
            assert payload == {"TypeCode": 1}
            child = {"Text": "股份下属电厂", "Value": 61, "Items": []}
            target = {"Text": "申能股份有限公司", "Value": 6, "Items": [child]}
            other = {"Text": "集团其他单位", "Value": 21, "Items": []}
            nodes = [target, other]
            if self.failure == "missing_target":
                nodes = [other]
            elif self.failure == "duplicate":
                nodes.append(child)
            return {
                "Code": 200,
                "Data": {"Type": {"TypeCode": 1, "Text": "招聘单位", "Items": nodes}},
            }
        response = await super().request(url, payload=payload, detail=detail)
        for row in response["Data"]:
            unit = "集团其他单位" if int(row["Id"]) % 2 else "股份下属电厂"
            row.update(
                Org=unit,
                ClassificationOne=unit,
                ClassificationTwo="生产运行类",
                CategoryId="2",
                JobAdName=f"工程师{row['Id']}",
                Duty="运行设备",
                Require="本科及以上",
                Degree="本科",
                Kind="全职",
            )
            if row["Id"] == "0":
                if self.failure == "unknown_unit":
                    row["Org"] = row["ClassificationOne"] = "树外单位"
                elif self.failure == "mismatched_unit":
                    row["ClassificationOne"] = "集团其他单位"
        return response


def source() -> Source:
    return Source(
        source_id="COM0471",
        company_id="COM0471",
        company="申能股份有限公司",
        url="https://shenergy.zhiye.com/custom/campus",
    )


async def test_shenergy_full_group_pagination_with_listed_subtree(now: datetime) -> None:
    replay = ShenergyReplay()
    result = await ShenergyListedCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [0, 1]
    scope = result.scopes[0]
    assert scope.unique == scope.expected == 21
    assert scope.details == 11 and scope.skipped_out_of_scope == 10
    assert {job.unit for job in result.jobs} == {"股份下属电厂"}
    assert {job.category_raw for job in result.jobs} == {"生产运行类"}
    assert all(job.duties == "运行设备" for job in result.jobs)
    assert replay.details == []


@pytest.mark.parametrize(
    "failure", ["missing_target", "duplicate", "unknown_unit", "mismatched_unit"]
)
async def test_shenergy_ambiguous_boundary_never_completes(now: datetime, failure: str) -> None:
    result = await ShenergyListedCampus(source(), ShenergyReplay(failure=failure), now).collect()
    assert result.coverage_issues()
    assert not result.jobs


async def test_shenergy_rejects_partial_unit_filter(now: datetime) -> None:
    class Filtered(ShenergyReplay):
        async def observed(self, needle: str) -> dict[str, Any]:
            response = await super().observed(needle)
            if "GetJobAdPageList" in needle:
                payload = json.loads(response["post_data"])
                payload["ClassificationOne"] = [61]
                response["post_data"] = json.dumps(payload)
            return response

    result = await ShenergyListedCampus(source(), Filtered(), now).collect()
    assert result.coverage_issues()
    assert not result.jobs
