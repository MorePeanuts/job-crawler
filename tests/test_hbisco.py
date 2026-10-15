import json
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.hbisco import HbiscoCampus
from job_crawler.models import Source


class Session:
    last_evidence = "fixture"
    prefix = "https://biz.hbisco.com/stage-api/apply/recruitment/position"

    def __init__(self, *, bad_unit: bool = False, total_drift: bool = False):
        self.bad_unit = bad_unit
        self.total_drift = total_drift
        self.rows = [
            {
                "id": str(i),
                "hbisPositiont": f"工程师{i}",
                "hbisDemandOrgBelongcompanyName": "唐钢公司" if i % 2 else "河钢集团",
            }
            for i in range(1, 12)
        ]

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://biz.hbisco.com/gf/hrpc/recruit/campus"

    async def observed(self, needle: str) -> dict[str, Any]:
        if needle.endswith("/list?"):
            return {
                "url": f"{self.prefix}/list?hbisMediaOutlet=A&hbisRequirementType=A&pageNum=1&pageSize=10"
            }
        assert needle.endswith("/filterOptions?")
        return {
            "url": f"{self.prefix}/filterOptions?hbisMediaOutlet=A&hbisRequirementType=A",
            "body": json.dumps(
                {
                    "success": True,
                    "code": "00000",
                    "data": {
                        "company": [
                            {"name": "河钢集团", "code": "1"},
                            {"name": "唐钢公司", "code": "287"},
                        ]
                    },
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        parts = urlsplit(url)
        params = parse_qs(parts.query)
        if parts.path.endswith("/list"):
            page = int(params["pageNum"][0])
            return {
                "success": True,
                "code": "00000",
                "data": {
                    "totalCount": 12 if page == 2 and self.total_drift else 11,
                    "pageNo": page,
                    "pageSize": 10,
                    "lastPage": page == 2,
                    "rows": self.rows[(page - 1) * 10 : page * 10],
                },
            }
        assert parts.path.endswith("/detail") and detail
        key = params["id"][0]
        row = self.rows[int(key) - 1]
        unit = "未知单位" if self.bad_unit and key == "2" else row["hbisDemandOrgBelongcompanyName"]
        return {
            "success": True,
            "code": "00000",
            "data": {
                **row,
                "hbisDemandOrgBelongcompanyName": unit,
                "hbisRequirementType": "A",
                "hbisMediaOutlet": ",A,B,",
                "hbisJobDuties": "负责钢材研发",
                "hbisJobReqs": "" if key == "2" else "硕士研究生以上学历",
                "hbisProReqs": "冶金工程",
                "hbisWorkLocation": "河北省唐山市",
                "hbisDueDate": "2027-05-31",
                "createtime": "2026-09-17 10:38:11",
                "hbisEffectiveDate": "2026-09-17",
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0067",
        company_id="COM0067",
        company="河钢集团有限公司",
        url="https://biz.hbisco.com/gf/hrpc/recruit/campus",
    )


async def test_hbisco_all_pages_and_detail_identity(now: datetime) -> None:
    result = await HbiscoCampus(source(), Session(), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == result.scopes[0].details == 11
    assert len({job.source_key for job in result.jobs}) == 11
    assert all(not job.published for job in result.jobs)
    assert all(job.deadline == "2027-05-31" for job in result.jobs)
    assert {job.unit for job in result.jobs} == {"唐钢公司", "河钢集团"}
    assert "专业要求：冶金工程" in result.jobs[1].requirements


async def test_hbisco_bad_detail_unit_retains_other_jobs(now: datetime) -> None:
    result = await HbiscoCampus(source(), Session(bad_unit=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 10
    assert result.scopes[0].details == 10


async def test_hbisco_total_drift_stops_after_first_page(now: datetime) -> None:
    result = await HbiscoCampus(source(), Session(total_drift=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 10
    assert not result.scopes[0].terminal
