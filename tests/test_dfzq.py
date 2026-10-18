"""A current empty catalog needs API, identity, no filters and visible evidence."""

import copy
import json
from typing import NotRequired, TypedDict, cast

import pytest

from job_crawler.adapters.dfzq import ENDPOINT, QUERY, ROOT, DfzqCampus
from job_crawler.models import Source
from job_crawler.transport import Session


class Stats(TypedDict):
    orgId: str
    total: NotRequired[int]


class CatalogData(TypedDict):
    jobStats: Stats
    jobs: list[dict[str, str]]


class Response(TypedDict):
    code: int
    codeType: int
    data: CatalogData
    msg: str
    success: bool


EMPTY: Response = {
    "code": 0,
    "codeType": 0,
    "data": {"jobStats": {"orgId": "dfzq", "total": 0}, "jobs": []},
    "msg": "成功",
    "success": True,
}


class Page:
    def __init__(self, fault):
        self.fault = fault

    async def evaluate(self, script):
        assert "TurboApply" in script
        return "0123456789abcdef"

    def get_by_text(self, text, *, exact):
        assert text == "尚无任何相关职位" and exact
        return self

    async def wait_for(self, **kwargs):
        assert kwargs == {"timeout": 15000}
        if self.fault == "shell":
            raise ValueError("empty state not visible")

    async def content(self):
        return "<html>尚无任何相关职位</html>"


class Replay:
    last_evidence = "entry"

    def __init__(self, fault=""):
        self.fault = fault
        self.page = Page(fault)
        self.calls = []

    async def open(self, url, *, ready_endpoints=()):
        assert url == ROOT + DfzqCampus.path and ready_endpoints == (ENDPOINT,)

    async def observed_path(self, path):
        assert path == ENDPOINT
        query = copy.deepcopy(QUERY)
        body = copy.deepcopy(EMPTY)
        if self.fault == "filter":
            query["keyword"] = "投资"
        if self.fault == "tenant":
            query["siteId"] = 5546
        if self.fault == "response_tenant":
            body["data"]["jobStats"]["orgId"] = "other"
        if self.fault == "business":
            body["success"] = False
        if self.fault == "rows":
            body["data"]["jobs"] = [{"id": "x"}]
        if self.fault == "nonzero":
            body["data"]["jobStats"]["total"] = 1
            body["data"]["jobs"] = [{"id": "x"}]
        if self.fault == "missing":
            del body["data"]["jobStats"]["total"]
        self.last_evidence = "observed-list"
        return {"url": ROOT + path, "post_data": json.dumps(query), "body": json.dumps(body)}

    async def request(self, url, *, payload):
        assert url == ROOT + ENDPOINT and payload == QUERY
        self.calls.append(url)
        self.last_evidence = "refreshed-list"
        body = copy.deepcopy(EMPTY)
        if self.fault == "drift":
            body["data"]["jobStats"]["total"] = 1
            body["data"]["jobs"] = [{"id": "x"}]
        return body

    def snapshot(self, label, html):
        assert label == "dfzq-campus-empty" and "尚无任何相关职位" in html
        return "visible-empty"


def adapter(now, replay):
    return DfzqCampus(
        Source(
            source_id="COM0500",
            company_id="COM0500",
            company="东方证券股份有限公司",
            url=ROOT + DfzqCampus.path,
        ),
        cast(Session, replay),
        now,
    )


@pytest.mark.asyncio
async def test_verified_zero_requires_live_refresh_and_page_evidence(now):
    r = Replay()
    result = await adapter(now, r).collect()
    assert not result.coverage_issues() and not result.jobs
    scope = result.scopes[0]
    assert scope.expected == scope.listed == scope.unique == scope.details == 0
    assert scope.terminal and scope.evidence == ["observed-list", "refreshed-list", "visible-empty"]
    assert len(r.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "filter",
        "tenant",
        "response_tenant",
        "business",
        "rows",
        "nonzero",
        "missing",
        "shell",
        "drift",
    ],
)
async def test_unverified_or_future_nonzero_catalog_is_never_empty_success(now, fault):
    result = await adapter(now, Replay(fault)).collect()
    assert result.issues and result.coverage_issues()
    assert not any(s.terminal for s in result.scopes)
    if fault == "nonzero":
        assert result.issues[0].code == "unsupported_scope" and result.scopes[0].expected == 1


@pytest.mark.asyncio
async def test_internship_source_must_not_be_relabelled_campus(now):
    a = adapter(now, Replay())
    a.source.url = ROOT + "/campus_apply/dfzq/5546#/jobs"
    result = await a.collect()
    assert result.issues and not result.scopes
