from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from job_crawler.adapters.foxconn import FoxconnCampus
from job_crawler.filtering import select
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture"

    def __init__(self, failure: str = ""):
        self.failure = failure
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url.endswith("CompFoxconnPagerecruit_School")

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == FoxconnCampus.endpoint
        return {
            "url": f"https://{FoxconnCampus.host}{needle}?recruitType=1&brandCode=1&page=1&rowSize=50&positionType=&comPart=&sicCorpCode=&releaseTime=&projectId=&workPlace=&keyWord=&site="
            + ("local" if self.failure == "filter" else "")
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is None and not detail
        page = int(parse_qs(urlsplit(url).query)["page"][0])
        self.pages.append(page)
        self.last_evidence = f"page-{page}"
        start = (page - 1) * 10 if self.failure != "duplicate" else 0
        rows = [
            {
                "postId": i,
                "postName": "Rayprus-通用岗位",
                "recruitType": 1,
                "orgName": "Rayprus",
                "workType": "全职",
                "workPlace": "深圳市",
                "education": "本科及以上",
                "postType": "通用类",
                "workContent": "覆盖研发、工程技术、项目管理等近百个岗位",
                "serviceCondition": "2027届毕业生",
                "publishDate": "2026-10-13",
                "endDate": "2026-10-18",
            }
            for i in range(start, min(start + 10, 11))
        ]
        if self.failure == "type":
            rows[0]["recruitType"] = 2
        if self.failure == "body":
            del rows[0]["serviceCondition"]
        return {
            "req_state": 9200,
            "page": page,
            "rowSize": 10,
            "pageCount": 2,
            "rowCount": 11,
            "postList": rows,
        }


def source() -> Source:
    return Source(
        source_id="COM0005",
        company_id="COM0005",
        company="鸿海精密工业股份有限公司",
        url="https://foxconn.hotjob.cn/",
    )


async def test_full_pagination_generic_jobs_stay_single_rows(now: datetime) -> None:
    replay = Replay()
    result = await FoxconnCampus(source(), replay, now).collect()
    assert not result.coverage_issues() and replay.pages == [1, 2]
    assert len(result.jobs) == 11
    job = result.jobs[-1]
    assert job.source_key == "10" and job.unit == "Rayprus"
    assert "postId=10" in job.source_url and job.evidence == ["page-2"]
    assert job.duties == "覆盖研发、工程技术、项目管理等近百个岗位"
    assert select(job, "all", now.replace(year=2026, month=10, day=18)).kind == "include"


@pytest.mark.parametrize("failure", ["duplicate", "type", "body", "filter"])
async def test_bad_catalog_never_complete(now: datetime, failure: str) -> None:
    result = await FoxconnCampus(source(), Replay(failure), now).collect()
    assert result.coverage_issues()
