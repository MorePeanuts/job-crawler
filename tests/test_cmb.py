"""Contract replays; positive graduate samples are synthetic, not live acceptance."""

import json
from datetime import datetime
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import pytest

from job_crawler.adapters.cmb import API, INFO, LIST, TYPE, CmbCampus, detail_fields
from job_crawler.incremental import IncrementalSource
from job_crawler.models import Job, Scope, Source
from job_crawler.transport import CrawlError, Session


def row(key: int) -> dict[str, Any]:
    return {
        "publishGID": str(key),
        "jobDisplay": f"培养生{key}",
        "branchCodeName": "广州分行",
        "locationName": "广州市",
        "expiredOn": "2026-12-31",
        "longTermRecruitment": False,
    }


def detail_value(key: int) -> dict[str, Any]:
    return {
        **row(key),
        "recruitmentTypeID": TYPE,
        "jobResponsibility": "<p>培养综合金融业务能力。</p>",
        "jobRequirement": "<p>面向应届毕业生，本科及以上。</p>",
    }


def success(value: dict[str, Any]) -> dict[str, Any]:
    return {"returnCode": "SUC0000", "errorMsg": None, "body": value}


class Replay:
    last_evidence = "list-1"

    def __init__(self, total: int = 21, failure: str = "") -> None:
        self.total = total
        self.failure = failure
        self.page = self
        self.pages: list[int] = []
        self.details: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url.endswith(TYPE)
        assert ready_endpoints == (LIST, INFO)

    async def content(self) -> str:
        return "页面加载中" if self.failure == "empty_dom" else "未找到相关职位"

    async def observed(self, endpoint: str) -> dict[str, Any]:
        if endpoint == INFO:
            return {
                "url": INFO,
                "body": json.dumps(
                    success(
                        {
                            "recruitingOrgList": ["机构"] if self.failure == "empty_org" else [],
                            "recruitingCityList": [],
                        }
                    )
                ),
            }
        assert endpoint == LIST
        payload = {
            "orgIdList": ["filtered"] if self.failure == "filter" else [],
            "keywords": "",
            "locationIdList": [],
            "jobTypeIdList": [],
            "recruitmentTypeId": TYPE,
            "pageIndex": 1,
            "pageSize": 10,
        }
        return {"url": LIST, "post_data": json.dumps(payload), "body": json.dumps(self.catalog(1))}

    def catalog(self, page: int) -> dict[str, Any]:
        self.pages.append(page)
        self.last_evidence = f"list-{page}"
        start = (page - 1) * 10
        if self.failure == "duplicate" and page == 2:
            start = 0
        rows = [row(i) for i in range(start, min(start + 10, self.total))]
        if self.failure == "short" and page == 2:
            rows.pop()
        return success(
            {"total": self.total + (self.failure == "count" and page == 2), "data": rows}
        )

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]:
        if url == LIST:
            assert payload is not None and payload["recruitmentTypeId"] == TYPE
            assert payload["orgIdList"] == payload["locationIdList"] == []
            return self.catalog(payload["pageIndex"])
        assert url.startswith(API + "getDetail?") and detail
        key = int(parse_qs(urlsplit(url).query)["publishId"][0])
        self.details.append(key)
        self.last_evidence = f"detail-{key}"
        if key == 0 and self.failure in {"closed", "business"}:
            return {
                "returnCode": "EZPREC0001",
                "errorMsg": "该职位已过期, 请刷新后重试"
                if self.failure == "closed"
                else "服务错误",
                "body": None,
            }
        value = detail_value(key)
        if key == 0 and self.failure == "identity":
            value["jobDisplay"] = "其他岗位"
        return success(value)


def adapter(replay: Replay) -> CmbCampus:
    return CmbCampus(
        Source(
            source_id="COM0055",
            company_id="COM0055",
            company="招商银行股份有限公司",
            url="https://career.cmbchina.com/",
        ),
        cast(Session, replay),
        datetime(2026, 10, 18),
    )


@pytest.mark.asyncio
async def test_full_three_pages_and_source_fields() -> None:
    replay = Replay()
    result = await adapter(replay).collect()
    assert not result.issues
    assert replay.pages == [1, 2, 3] and replay.details == list(range(21))
    scope = result.scopes[0]
    assert scope.expected == scope.listed == scope.unique == scope.details == 21
    assert scope.terminal
    job = result.jobs[-1]
    assert job.evidence == ["list-3", "detail-20"]
    assert job.title == "培养生20" and job.location == "广州市"
    assert not job.published and not job.education and not job.address
    assert job.deadline == "2026-12-31" and job.duties == "培养综合金融业务能力。"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["", "empty_dom", "empty_org"])
async def test_zero_requires_complete_org_city_and_page_evidence(failure: str) -> None:
    replay = Replay(0, failure)
    result = await adapter(replay).collect()
    assert bool(result.issues) == bool(failure)
    assert result.scopes[0].terminal == (not failure)
    assert not result.jobs and not replay.details


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["duplicate", "count", "short", "filter"])
async def test_incomplete_or_filtered_directory_cannot_pass(failure: str) -> None:
    result = await adapter(Replay(failure=failure)).collect()
    assert result.issues
    assert not any(s.terminal for s in result.scopes)
    assert len(result.jobs) == (0 if failure == "filter" else 10)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["closed", "business", "identity"])
async def test_closed_status_is_exact_and_partial_details_are_preserved(failure: str) -> None:
    result = await adapter(Replay(2, failure)).collect()
    scope = result.scopes[0]
    assert scope.terminal and scope.details == 1
    if failure == "closed":
        assert not result.issues and scope.skipped_closed == 1
        assert len(result.jobs) == 2 and not result.jobs[0].visible
    else:
        assert result.issues and not scope.skipped_closed
        assert len(result.jobs) == 1 and result.jobs[0].source_key == "1"


@pytest.mark.parametrize("change", ["scope", "identity", "location", "attachment", "empty"])
def test_detail_scope_identity_and_body_contract(change: str) -> None:
    value = detail_value(0)
    if change == "scope":
        value["recruitmentTypeID"] = "intern"
    elif change == "identity":
        value["publishGID"] = "other"
    elif change == "location":
        value["locationName"] = "北京市"
    elif change == "attachment":
        value["jobRequirement"] = '<img src="requirements.png">'
    else:
        value.update(jobResponsibility=None, jobRequirement=None)
    with pytest.raises(CrawlError):
        detail_fields(row(0), value)


def test_long_term_does_not_use_historical_deadline() -> None:
    from job_crawler.adapters.cmb import listing_fields

    value = row(0)
    value.update(longTermRecruitment=True, expiredOn="2020-01-01")
    assert listing_fields(value)["deadline"] == ""


class Reuse:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def before_detail(
        self,
        entity: str,
        listing: object,
        scope: Scope,
        evidence: str,
        job: Job | None,
    ) -> list[Job]:
        assert job is not None and evidence == "list-1" and listing == row(0)
        self.calls.append(entity)
        scope.reused_details += 1
        return [job]


@pytest.mark.asyncio
async def test_incremental_hook_can_reuse_without_detail_request() -> None:
    replay = Replay(1)
    crawler = adapter(replay)
    reuse = Reuse()
    crawler.incremental = cast(IncrementalSource, reuse)
    result = await crawler.collect()
    assert not result.issues and len(result.jobs) == 1
    assert reuse.calls == ["job:0"] and not replay.details
    assert result.scopes[0].reused_details == 1
