import json
from datetime import datetime
from typing import Any

import pytest

from job_crawler.adapters.shengtun import BRANCHES, ShengtunMiningCampus
from job_crawler.adapters.zhaopin import API
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture"

    def __init__(self, failure: str = ""):
        self.failure = failure
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://shengtun2027.zhaopin.com/index.html"

    async def observed(self, needle: str) -> dict[str, Any]:
        return {
            "url": API
            if needle == API
            else "https://fe.zhaopin.com/grace/api/dsc/get-search-aggregation",
            "post_data": json.dumps(
                {"orgNumbers": "105807", "jobSource": 2, "pageIndex": 1, "pageSize": 12}
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None and not detail
        if "aggregation" in url:
            assert payload["facetFields"] == ["SOU_XY_ORG_ID"]
            self.last_evidence = "tree"
            units = [
                {
                    "name": name,
                    "code": code,
                    "count": 17,
                    "extend": {"number": number, "parentId": "105807"},
                }
                for number, (name, code) in BRANCHES.items()
            ]
            if self.failure == "counts":
                units[0]["count"] = 18
            if self.failure == "unknown_tree":
                units[0]["name"] = "新板块"
            return {"code": 200, "data": {"itemMap": {"SOU_XY_ORG_ID": units}}}
        assert payload["campusParentDepartmentIds"] == "" and payload["orgDepartmentIds"] == []
        page = int(payload["pageIndex"])
        size = int(payload["pageSize"])
        self.pages.append(page)
        start = (page - 1) * size if self.failure != "duplicate" else 0
        self.last_evidence = f"list-{page}"
        rows = []
        for i in range(start, min(start + size, 51)):
            number = list(BRANCHES)[i % 3]
            name, code = BRANCHES[number]
            rows.append(
                {
                    "company": {
                        "companyId": 105807,
                        "companyNumber": number,
                        "campusOrgName": name,
                        "slaveDisplayOrgName": "深圳盛屯集团有限公司",
                        "campusDepartment": {
                            "parentId": 0 if self.failure == "parent" and i == 1 else code,
                            "name": name + "总部",
                        },
                    },
                    "job": {
                        "jobNumber": str(i),
                        "positionSourceType": 2,
                        "title": "工程师",
                        "detail": "职责：研发\n任职要求：本科",
                        "url": f"https://xiaoyuan.zhaopin.com/job/{i}",
                        "minEducationName": "本科",
                    },
                }
            )
        return {
            "code": 200,
            "data": {
                "pageInfo": {"totalNum": 51, "totalPage": 2, "pageIndex": page, "pageSize": size},
                "jobList": rows,
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0450",
        company_id="COM0450",
        company="盛屯矿业集团股份有限公司",
        url="https://shengtun2027.zhaopin.com/index.html",
    )


async def test_only_mining_included_with_complete_group_counts(now: datetime) -> None:
    replay = Replay()
    result = await ShengtunMiningCampus(source(), replay, now).collect()
    assert not result.coverage_issues() and replay.pages == [1, 2]
    scope = result.scopes[0]
    assert scope.unique == 51 and scope.details == 17 and scope.skipped_out_of_scope == 34
    assert len(result.jobs) == 17 and all(job.unit == "盛屯矿业总部" for job in result.jobs)
    assert all(job.company == "盛屯矿业集团股份有限公司" for job in result.jobs)
    assert all(job.published == job.deadline == "" for job in result.jobs)
    assert all("tree" in job.evidence for job in result.jobs)


@pytest.mark.parametrize("failure", ["counts", "unknown_tree", "duplicate", "parent"])
async def test_changed_scope_or_paging_fails(now: datetime, failure: str) -> None:
    result = await ShengtunMiningCampus(source(), Replay(failure), now).collect()
    assert result.coverage_issues()
    if failure == "parent":
        assert len(result.jobs) == 1
