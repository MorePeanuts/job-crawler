import json
from datetime import datetime
from typing import Any

import pytest

from job_crawler.adapters.sinopec import SinopecCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture"

    def __init__(self, failure: str = ""):
        self.page = self
        self.failure = failure
        self.clicked = False
        self.requests: list[tuple[str, int]] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://job.sinopec.com/#/school/recruitmentPositions"

    def get_by_text(self, value: str, *, exact: bool) -> "Replay":
        assert value == "招聘岗位" and exact
        return self

    async def click(self, **kwargs: int) -> None:
        self.clicked = True

    async def observed(self, needle: str) -> dict[str, Any]:
        if "Position" in needle:
            assert self.clicked
        return {
            "url": f"https://job.sinopec.com/api/upgrade{needle}",
            "post_data": json.dumps(
                {"page": 1, "limit": 20, "keyword": "研发" if self.failure == "filter" else ""}
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None and not detail
        page = int(payload["page"])
        kind = "units" if "YpList" in url else "jobs"
        self.requests.append((kind, page))
        self.last_evidence = f"{kind}-{page}"
        start = (page - 1) * 20
        if self.failure == "duplicate" and kind == "jobs":
            start = 0
        rows = []
        for i in range(start, min(start + 20, 21)):
            if kind == "units":
                rows.append(
                    {
                        "jobId": f"j{i}",
                        "deptId": str(i),
                        "deptName": f"单位{i}",
                        "postNum": 2 if self.failure == "unit_count" and i == 0 else 1,
                    }
                )
            else:
                rows.append(
                    {
                        "id": str(i),
                        "deptCode": "unknown" if self.failure == "unit" and i == 0 else str(i),
                        "deptName": f"单位{i}",
                        "jobPosition": f"工程师{i}",
                        "workAddr": "北京市",
                        "educationNorm": "硕士研究生",
                        "positionType": "主体专业岗位",
                        "specialtyNorm": "化学工程",
                        "foreignNorm": "六级425分",
                        "otherNorm": "能接受基层锻炼",
                        "timeEnd": "2026-10-28 17:00:00",
                    }
                )
        if self.failure == "body" and kind == "jobs" and page == 1:
            del rows[0]["otherNorm"]
        if self.failure == "empty" and kind == "jobs" and page == 2:
            rows = []
        return {
            "code": "failed" if self.failure == "business" else "S000000",
            "data": {"total": 21, "size": 20, "current": page, "pages": 2, "records": rows},
        }


def source() -> Source:
    return Source(
        source_id="COM0003",
        company_id="COM0003",
        company="中国石油化工集团有限公司",
        url="https://job.sinopec.com/",
    )


async def test_units_and_jobs_all_pages_keep_missing_fields(now: datetime) -> None:
    replay = Replay()
    result = await SinopecCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.requests == [("units", 1), ("units", 2), ("jobs", 1), ("jobs", 2)]
    assert len(result.jobs) == 21
    assert all(job.published == job.duties == "" for job in result.jobs)
    job = result.jobs[-1]
    assert job.requirements == "专业要求：化学工程\n外语要求：六级425分\n其他要求：能接受基层锻炼"
    assert job.unit == "单位20" and job.evidence == ["jobs-2"]
    assert job.source_url.endswith("?postId=20")
    assert job.deadline == "2026-10-28 17:00:00"


@pytest.mark.parametrize(
    "failure", ["duplicate", "unit", "unit_count", "empty", "filter", "business", "body"]
)
async def test_incomplete_or_mismatched_catalog_never_succeeds(now: datetime, failure: str) -> None:
    result = await SinopecCampus(source(), Replay(failure), now).collect()
    assert result.coverage_issues()
    if failure in {"unit", "body"}:
        assert len(result.jobs) == 20
