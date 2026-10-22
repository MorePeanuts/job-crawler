"""Meditrust mobile catalog pagination and detail identity replay."""

import json
from datetime import datetime
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.base import query
from job_crawler.adapters.meditrust import INFO, LIST, PARAMS, MeditrustCampus
from job_crawler.models import Source
from job_crawler.transport import Session


class Replay:
    last_evidence = "list"

    def __init__(self, *, wrong_detail: bool = False, duplicate: bool = False):
        self.wrong_detail = wrong_detail
        self.duplicate = duplicate
        self.rows = [
            {
                "JobAdId": 100 + index,
                "JobAdName": "实习生" if index == 0 else "【2027届校招】工程师",
                "TenantId": 602524,
                "CategoryId": 2,
                "KindId": 3 if index == 0 else 1,
                "KindName": "实习" if index == 0 else "全职",
                "ToPostDate": "2026-10-01",
                "ToEndDate": "2222-02-02",
                "Class1Name": "研发",
            }
            for index in range(2)
        ]

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url.endswith("/yjlist.html")

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == "/JobAd/_SearchJobAd"
        return {
            "url": query(LIST, **PARAMS, pi=1, ps=10),
            "body": json.dumps({"DataResult": self.rows}),
        }

    async def request(self, url: str, *, detail: bool = False) -> dict[str, Any]:
        params = parse_qs(urlsplit(url).query)
        if url.startswith(LIST):
            page = int(params["pi"][0])
            rows = self.rows if page == 1 else [self.rows[0]] if self.duplicate else []
            self.last_evidence = f"page-{page}"
            return {"DataResult": rows, "RowCount": len(rows), "CurPageSize": page}
        assert url.startswith(INFO) and detail
        key = int(params["adid"][0])
        row = self.rows[key - 100]
        self.last_evidence = f"detail-{key}"
        return {
            "TenantId": row["TenantId"],
            "JobAdId": key + 1 if self.wrong_detail and key == 101 else key,
            "JobAdName": row["JobAdName"],
            "Kind": row["KindId"],
            "KindName": row["KindName"],
            "PostDateStr": row["ToPostDate"],
            "EndTimeStr": "-",
            "DutyStr": "设计产品",
            "RequireStr": "本科毕业",
            "Department": "研发部",
            "LocName": "上海市",
            "DegreeStr": "本科",
            "DetailAddress": "",
        }


def source() -> Source:
    return Source(
        source_id="COM0680",
        company_id="COM0680",
        company="镁信健康",
        url="https://meditrusthealth.m.zhiye.com/yjlist.html",
    )


async def test_meditrust_complete_catalog_filters_internship(now: datetime) -> None:
    result = await MeditrustCampus(source(), cast(Session, Replay()), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == result.scopes[0].details == 2
    assert result.scopes[0].terminal
    assert [job.work_type for job in result.jobs] == ["实习", "校招"]
    assert result.jobs[1].published == "2026-10-01"
    assert result.jobs[1].requirements == "本科毕业"


async def test_meditrust_rejects_duplicate_page_and_detail_mismatch(now: datetime) -> None:
    duplicate = await MeditrustCampus(
        source(), cast(Session, Replay(duplicate=True)), now
    ).collect()
    assert duplicate.coverage_issues() and not duplicate.scopes[0].terminal
    mismatch = await MeditrustCampus(
        source(), cast(Session, Replay(wrong_detail=True)), now
    ).collect()
    assert mismatch.coverage_issues()
    assert mismatch.scopes[0].details == 1
