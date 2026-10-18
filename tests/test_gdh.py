"""Observed public metadata with synthetic narratives and generated pagination rows."""

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import pytest

from job_crawler.adapters.base import query
from job_crawler.adapters.gdh import ALL, ENTRY, INFO, LIST, QUERY, GdhMobileCampus, fields
from job_crawler.incremental import IncrementalSource
from job_crawler.models import Job, Scope, Source
from job_crawler.transport import Session

DATA = json.loads((Path(__file__).parent / "fixtures/gdh/business.json").read_text())
SEGMENTS = '<a href="/recruitment.html?c2=3_-1&k=all">全部职位</a>' + "".join(
    f'<a href="/recruitment.html?c2=3_{n}&k=unit">{name}</a>'
    for n, name in enumerate(["集团总部", "水务环境", "城建运营", "食品生物", "产业投资"], 1)
)


class Replay:
    last_evidence = "initial"

    def __init__(self, count: int = 140, fault: str = ""):
        self.page = self
        self.url = ""
        self.count = count
        self.fault = fault
        self.opened: list[str] = []
        self.requested: list[str] = []
        self.rows = []
        for index in range(count):
            item = deepcopy(DATA["listing"])
            item.update(
                JobAdId=10000 + index, JobAdName=f"岗位{index}", Department=f"招聘子单位{index}"
            )
            if index == 0:
                item.update(KindId=3, KindName="实习")
            if index == 101:
                item["Categories"][-1].update(
                    CategoryId=19, CategoryName="广东省水利电力勘测设计研究院有限公司"
                )
                item["Class2Name"] = "招聘区域:广东省水利电力勘测设计研究院有限公司"
            self.rows.append(item)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.opened.append(url)
        self.url = url

    async def content(self) -> str:
        if self.url == ENTRY:
            return SEGMENTS.replace("食品生物", "未知板块") if self.fault == "branch" else SEGMENTS
        return "校园招聘岗位" + ("暂无职位" if self.count == 0 and self.fault != "blank" else "")

    def snapshot(self, label: str, html: str) -> str:
        self.last_evidence = label
        return label

    async def observed(self, needle: str) -> dict[str, Any]:
        if needle == LIST:
            params = {**QUERY, "jc": "1" if self.fault == "filter" else "2"}
            return {
                "url": query(LIST, **params),
                "body": json.dumps({"RowCount": self.count, "DataResult": self.rows[:100]}),
            }
        ident = parse_qs(urlsplit(self.url).query)["adId"][0]
        return {"url": query(INFO, adid=ident, **{"in": 1})}

    async def request(self, url: str, *, detail: bool = False) -> dict[str, Any]:
        self.requested.append(url)
        params = parse_qs(urlsplit(url).query)
        if url.startswith(LIST):
            assert params["ps"] == ["100"] and params["jc"] == ["2"] and params["c2"] == ["3_-1"]
            page = int(params["pi"][0])
            rows = deepcopy(self.rows[(page - 1) * 100 : page * 100])
            total = self.count if rows else 0
            if page == 2:
                if self.fault == "repeat":
                    rows[0] = deepcopy(self.rows[0])
                if self.fault == "short":
                    rows = rows[:-1]
                if self.fault == "count":
                    total += 1
                if self.fault == "last_nonempty":
                    rows = [deepcopy(self.rows[0])]
            if page == 1 and rows:
                if self.fault == "tenant":
                    rows[0]["TenantId"] = 999
                if self.fault == "category":
                    rows[0]["CategoryId"] = 1
                if self.fault == "kind":
                    rows[0]["KindName"] = "未知"
            self.last_evidence = f"list-{page}"
            return {
                "DataResult": rows,
                "RowCount": total,
                "PageCount": 0,
                "PageSize": 0,
                "CurPageSize": 1,
            }
        ident = int(params["adid"][0])
        row = self.rows[ident - 10000]
        data = deepcopy(DATA["detail"])
        for key in ("JobAdId", "JobAdName", "Department"):
            data[key] = row[key]
        data["Categories"] = [
            {
                "TypeId": 3,
                "ConstValue": row["Categories"][-1]["CategoryId"],
                "ConstText": row["Categories"][-1]["CategoryName"],
            }
        ]
        if ident == 10001:
            if self.fault == "id":
                data["JobAdId"] += 1
            if self.fault == "title":
                data["JobAdName"] = "别的岗位"
            if self.fault == "unit":
                data["Department"] = "另一个单位"
            if self.fault == "detail_tenant":
                data["TenantId"] = 999
            if self.fault == "region":
                data["Categories"][0]["ConstValue"] += 1
            if self.fault == "date":
                data["PostDateStr"] = "2026-09-15"
            if self.fault == "deadline":
                data["EndTimeStr"] = "2026-12-01"
            if self.fault == "attachment":
                data["RequireStr"] = '<img src="requirements.png">'
            if self.fault == "missing":
                del data["RequireStr"]
            if self.fault == "network":
                raise TimeoutError("public detail unavailable")
        self.last_evidence = f"detail-{ident}"
        return data


def adapter(replay: Replay, now: datetime) -> GdhMobileCampus:
    return GdhMobileCampus(
        Source(
            source_id="COM0324", company_id="COM0324", company="广东粤海控股集团有限公司", url=ENTRY
        ),
        cast(Session, replay),
        now,
    )


async def test_cap_100_all_regions_140_then_explicit_empty(now: datetime) -> None:
    replay = Replay()
    result = await adapter(replay, now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 139
    scope = result.scopes[0]
    assert (
        scope.expected,
        scope.listed,
        scope.unique,
        scope.details,
        scope.skipped_out_of_scope,
        scope.terminal,
    ) == (140, 140, 140, 139, 1, True)
    assert len([u for u in replay.requested if u.startswith(LIST)]) == 3
    job = next(j for j in result.jobs if j.source_key == "10101")
    assert job.unit == "招聘子单位101" and "sldlkcsjyjy" in job.source_url
    assert job.company == "广东粤海控股集团有限公司"
    assert job.published == "2026-09-14" and job.deadline == job.address == ""
    assert job.location == "湛江市" and job.education == "本科及以上"
    assert job.duties == "维护机电设备。" and job.requirements == "本科及以上，机械、电气专业。"
    assert job.evidence == ["list-2", "detail-10101"]


@pytest.mark.parametrize(
    "fault", ["branch", "filter", "repeat", "short", "count", "tenant", "category", "kind"]
)
async def test_bad_catalog_never_complete(fault: str, now: datetime) -> None:
    result = await adapter(Replay(fault=fault), now).collect()
    assert result.coverage_issues()


async def test_extra_page_after_expected_total_is_not_success(now: datetime) -> None:
    result = await adapter(Replay(100, "last_nonempty"), now).collect()
    assert result.coverage_issues()


@pytest.mark.parametrize(
    "fault",
    [
        "id",
        "title",
        "unit",
        "detail_tenant",
        "region",
        "date",
        "deadline",
        "attachment",
        "missing",
        "network",
    ],
)
async def test_partial_detail_retains_other_jobs(fault: str, now: datetime) -> None:
    result = await adapter(Replay(4, fault), now).collect()
    assert result.coverage_issues() and len(result.jobs) == 2
    assert {j.source_key for j in result.jobs} == {"10002", "10003"}


@pytest.mark.parametrize("fault", ["", "blank"])
async def test_zero_requires_explicit_campus_empty_state(fault: str, now: datetime) -> None:
    result = await adapter(Replay(0, fault), now).collect()
    assert bool(result.coverage_issues()) == bool(fault)
    assert not result.jobs


def test_real_deadline_and_default_category_are_not_confused() -> None:
    row = deepcopy(DATA["listing"])
    detail = deepcopy(DATA["detail"])
    row["ToEndDate"] = detail["EndTimeStr"] = "2026-12-01"
    result = fields(row, detail)
    assert result["deadline"] == "2026-12-01"
    assert detail["Category"] == 0 and detail["IsEmpty"] is True


async def test_incremental_rechecks_all_pages_without_opening_detail(now: datetime) -> None:
    class Reuse:
        def before_detail(
            self,
            entity: str,
            listing: object,
            scope: Scope,
            evidence: str,
            listing_job: Job | None = None,
        ) -> list[Job]:
            assert listing_job and entity == "job:" + listing_job.source_key
            assert evidence.startswith("list-")
            scope.reused_details += 1
            return [listing_job]

    replay = Replay(4)
    instance = adapter(replay, now)
    instance.incremental = cast(IncrementalSource, Reuse())
    result = await instance.collect()
    assert not result.coverage_issues() and result.scopes[0].reused_details == 3
    assert replay.opened == [ENTRY, ALL]
    assert all(url.startswith(LIST) for url in replay.requested)
