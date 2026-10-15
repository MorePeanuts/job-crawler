import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.zjci import ZjciCampus
from job_crawler.models import Source


class Session:
    last_evidence = "fixture"

    def __init__(self, *, bad_status: bool = False):
        self.rows = [
            {
                "id": index,
                "category": 2,
                "processStatus": 1 if bad_status and index == 2 else 2,
                "positionName": f"工程师{index}",
                "enterprise": f"浙江建投成员单位{index}",
                "area": "华东区域",
                "responsibilities": "负责建筑项目",
                "requirements": "本科及以上学历",
                "startTime": "2026-09-15 00:00:00",
                "endTime": "2027-06-30 00:00:00",
            }
            for index in (1, 2)
        ]

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://www.cnzgc.com/home/join"

    async def observed(self, needle: str) -> dict[str, Any]:
        if needle.startswith("pageSize=500"):
            return {
                "url": "https://www.cnzgc.com/cnzgc/con/recruitments/listPage?currentPage=1&pageSize=500&type=2&siteId=ST-20241124222158",
                "body": json.dumps(
                    {
                        "code": 200,
                        "resData": {
                            "total": 2,
                            "pages": 1,
                            "currentPage": 1,
                            "result": self.rows,
                        },
                    }
                ),
            }
        assert needle.startswith("pageSize=10")
        return {"body": json.dumps({"resData": {"total": 2, "result": self.rows}})}

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError(f"unexpected request: {url}")


def source() -> Source:
    return Source(
        source_id="COM0229",
        company_id="COM0229",
        company="浙江省建设投资集团股份有限公司",
        url="https://www.cnzgc.com/home/join",
    )


async def test_zjci_full_catalog_and_missing_publication_date(now: datetime) -> None:
    result = await ZjciCampus(source(), Session(), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].details == 2
    assert [job.unit for job in result.jobs] == ["浙江建投成员单位1", "浙江建投成员单位2"]
    assert all(not job.published for job in result.jobs)
    assert all(job.deadline == "2027-06-30 00:00:00" for job in result.jobs)


async def test_zjci_changed_status_keeps_partial_result(now: datetime) -> None:
    result = await ZjciCampus(source(), Session(bad_status=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == len(result.jobs) == 1
