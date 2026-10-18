"""Frontend-contract replays; positive examples are synthetic, not live samples."""

import json
from datetime import datetime
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from job_crawler.adapters.sdhsg import API, LIST, QUERY, ROOT, SdhsgCampus, fields
from job_crawler.incremental import IncrementalSource
from job_crawler.models import Job, Scope, Source
from job_crawler.transport import Session


def row(key: int) -> dict[str, Any]:
    return {
        "id": key,
        "name": "工程技术岗",
        "orgName": "成员单位",
        "status": 1,
        "areaName": "济南市",
        "endTime": "2027-01-01 23:59:59",
    }


class Replay:
    last_evidence = "list-1"

    def __init__(self, total: int = 21, fault: str = ""):
        self.total, self.fault = total, fault
        self.page = self
        self.pages: list[int] = []
        self.details: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == ROOT + "/#/centralizedRecruitment" and ready_endpoints == (LIST,)

    async def content(self) -> str:
        return "加载中" if self.fault == "empty_dom" else "校招职位名称 暂无数据 共 0 条"

    async def observed(self, endpoint: str) -> dict[str, Any]:
        assert endpoint == LIST
        params = {**QUERY, "_t": "123"}
        if self.fault == "filter":
            params["orgId"] = "1"
        if self.fault == "social":
            params["recruitType"] = "2"
        return {"url": LIST + "?" + urlencode(params), "body": json.dumps(self.catalog(1))}

    def catalog(self, page: int) -> dict[str, Any]:
        self.pages.append(page)
        self.last_evidence = f"list-{page}"
        start = (page - 1) * 10
        if self.fault == "repeat" and page == 2:
            start = 0
        rows = [row(k) for k in range(start, min(start + 10, self.total))]
        if self.fault == "short" and page == 2:
            rows.pop()
        return {
            "code": 1 if self.fault == "list_business" else 0,
            "page": {
                "currPage": 1 if self.fault == "page" else page,
                "pageSize": 20 if self.fault == "size" else 10,
                "totalPage": (self.total + 9) // 10,
                "totalCount": self.total + (1 if self.fault == "count" and page == 2 else 0),
                "list": rows,
            },
        }

    async def request(self, url: str, *, detail: bool = False) -> dict[str, Any]:
        params = parse_qs(urlsplit(url).query, keep_blank_values=True)
        if url.startswith(LIST + "?"):
            assert params["recruitType"] == ["1"] and params["orgId"] == [""]
            return self.catalog(int(params["page"][0]))
        if url.startswith(API + "/hr/upload/getUploadFile?"):
            assert detail
            return {
                "code": 0,
                "uploadList": [{"name": "岗位附件"}] if self.fault == "attachment" else [],
            }
        assert url.startswith(API + "/hr/job/queryJob?") and detail
        key = int(params["id"][0])
        self.details.append(key)
        self.last_evidence = f"detail-{key}"
        item = {
            **row(key),
            "recruitType": 1,
            "educationName": "本科及以上",
            "provinceName": "山东省",
            "startTime": "2026-09-01",
            "createTime": "2026-08-30",
            "jobExplain": "<p>负责工程技术工作。</p>",
            "jobRequirement": "<p>应届毕业生。</p>",
            "specialtyValue": "土木工程",
            "politicalName": "不限",
        }
        if key == 0:
            if self.fault in {"id", "name", "orgName", "recruitType"}:
                item[self.fault] = "wrong"
            if self.fault in {"closed", "preview", "unknown_status"}:
                item["status"] = {"closed": 0, "preview": 2, "unknown_status": 9}[self.fault]
            if self.fault == "inline_attachment":
                item["jobExplain"] = '<img src="duties.png">'
            if self.fault == "empty_body":
                item["jobExplain"] = item["jobRequirement"] = ""
        return {"code": 1 if key == 0 and self.fault == "detail_business" else 0, "job": item}


def adapter(replay: Replay, now: datetime) -> SdhsgCampus:
    return SdhsgCampus(
        Source(source_id="COM0090", company_id="COM0090", company="山东高速集团有限公司", url=ROOT),
        cast(Session, replay),
        now,
    )


async def test_full_pages_identity_fields_and_no_invented_publication(now: datetime) -> None:
    replay = Replay()
    result = await adapter(replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2, 3] and replay.details == list(range(21))
    assert result.scopes[0].expected == result.scopes[0].unique == result.scopes[0].details == 21
    assert len(result.jobs) == 21
    assert result.jobs[0].published == "" and result.jobs[0].deadline == "2027-01-01 23:59:59"
    assert result.jobs[0].location == "山东省/济南市"
    assert "专业：土木工程" in result.jobs[0].requirements
    assert result.jobs[0].evidence[:2] == ["list-1", "detail-0"]


@pytest.mark.parametrize("fault", ["", "empty_dom", "filter", "social", "size", "list_business"])
async def test_zero_needs_business_and_campus_dom_evidence(fault: str, now: datetime) -> None:
    result = await adapter(Replay(0, fault), now).collect()
    assert bool(result.coverage_issues()) == bool(fault)
    if not fault:
        assert result.scopes[0].expected == 0 and result.scopes[0].terminal


@pytest.mark.parametrize(
    "fault",
    [
        "repeat",
        "short",
        "page",
        "size",
        "count",
        "id",
        "name",
        "orgName",
        "recruitType",
        "preview",
        "unknown_status",
        "attachment",
        "inline_attachment",
        "empty_body",
        "detail_business",
    ],
)
async def test_incomplete_catalog_or_detail_does_not_become_success(
    fault: str, now: datetime
) -> None:
    result = await adapter(Replay(21, fault), now).collect()
    assert result.coverage_issues()
    if fault in {
        "id",
        "name",
        "orgName",
        "recruitType",
        "preview",
        "unknown_status",
        "inline_attachment",
        "empty_body",
        "detail_business",
    }:
        assert len(result.jobs) == 20


async def test_only_explicit_ended_status_counts_as_closed(now: datetime) -> None:
    result = await adapter(Replay(1, "closed"), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].skipped_closed == 1 and not result.jobs[0].visible


def test_location_other_region_and_department_source_fields() -> None:
    result = fields(
        {
            "areaId": 991414,
            "provinceName": "未知",
            "areaName": "其他",
            "areaInfo": "肯尼亚内罗毕",
            "district": "1",
            "districtInfo": "项目驻地",
            "orgNameParent": "工程公司",
            "orgName": "国际事业部",
        }
    )
    assert result["location"] == "肯尼亚内罗毕 项目驻地"
    assert result["unit"] == "工程公司 / 国际事业部"


async def test_incremental_hook_can_reuse_but_cannot_skip_catalog(now: datetime) -> None:
    class Reuse:
        def before_detail(
            self,
            entity: str,
            listing: object,
            scope: Scope,
            evidence: str,
            listing_job: Job | None = None,
        ) -> list[Job]:
            assert listing_job is not None
            scope.reused_details += 1
            return [listing_job]

    replay = Replay(1)
    instance = adapter(replay, now)
    instance.incremental = cast(IncrementalSource, Reuse())
    result = await instance.collect()
    assert not result.coverage_issues() and replay.pages == [1] and not replay.details
    assert result.scopes[0].reused_details == 1
