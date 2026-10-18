"""A UI-generated query must prove channel, no filters, and a visible empty state."""

import json
from pathlib import Path
from typing import cast

import pytest

from job_crawler.adapters.bankgy import API, ENTRY, BankgyCampus, catalog
from job_crawler.models import Source
from job_crawler.transport import Session

FIXTURE = Path(__file__).parent / "fixtures/bankgy/empty.json"


def response(fault=""):
    data = json.loads(FIXTURE.read_text())
    result = data["return_data"]
    if fault == "business":
        data["succeed"] = False
    elif fault == "channel":
        data["hire_channel"] = "02"
    elif fault == "query":
        data["queryitem"][2]["value"] = "柜员"
    elif fault == "unit":
        result["posMap"]["需求单位`z0321"][0]["check"] = False
    elif fault == "missing":
        del result["position_data"]
    elif fault == "rows":
        result["position_data"] = [{"id": "x"}]
    elif fault == "nonzero":
        result["posTotal"] = 1
        result["position_data"] = [{"id": "x"}]
    elif fault == "boolean_total":
        result["posTotal"] = False
    elif fault in {"boardlist", "batchList"}:
        result[fault] = [{"id": "announcement"}]
    data["sessionHM"] = "must-not-be-persisted"
    return data


class Response:
    url = API
    status = 200

    def __init__(self, fault):
        self.fault = fault
        self.request = self
        self.method = "POST"

    async def json(self):
        return response(self.fault)


class ResponseInfo:
    def __init__(self, fault):
        self.fault = fault

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    @property
    def value(self):
        async def get():
            return Response(self.fault)

        return get()


class Page:
    url = ENTRY

    def __init__(self, fault):
        self.fault = fault
        self.calls = 0
        self.text = ""

    def get_by_text(self, text, *, exact):
        assert exact and text in {"搜索", "共0个职位", "暂无数据", "校园招聘"}
        self.text = text
        return self

    async def wait_for(self, **kwargs):
        if self.fault == "shell" and self.text == "暂无数据":
            raise ValueError("empty state missing")

    def get_by_placeholder(self, text, *, exact):
        assert exact and text == "职位名称、工作地点"
        return self

    async def input_value(self):
        return "柜员" if self.fault == "input" else ""

    def expect_response(self, predicate, *, timeout):
        assert timeout == 25000 and predicate(Response(""))
        fault = "nonzero" if self.fault == "changed" and self.calls == 1 else self.fault
        self.calls += 1
        return ResponseInfo(fault)

    async def click(self, **kwargs):
        assert self.text == "搜索"

    async def content(self):
        return "<html>校园招聘 共0个职位 暂无数据</html>"


class Replay:
    last_evidence = "entry"

    def __init__(self, fault):
        self.page = Page(fault)
        self.snapshots = []

    async def open(self, url):
        assert url == ENTRY

    def snapshot(self, name, content):
        assert "must-not-be-persisted" not in content
        self.snapshots.append(name)
        return name


def test_public_only():
    total, public = catalog(response())
    assert total == 0 and "sessionHM" not in public


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "",
        "business",
        "channel",
        "query",
        "unit",
        "missing",
        "rows",
        "nonzero",
        "boolean_total",
        "boardlist",
        "batchList",
        "changed",
        "shell",
        "input",
        "entry",
    ],
)
async def test_collect(fault, now):
    session = Replay(fault)
    source = Source(
        source_id="COM0485",
        company_id="COM0485",
        company="贵阳银行股份有限公司",
        url=ENTRY.replace(":7000", "") if fault == "entry" else ENTRY,
    )
    result = await BankgyCampus(source, cast(Session, session), now).collect()
    assert result.jobs == []
    if fault:
        assert result.issues and result.coverage_issues()
        if fault == "nonzero":
            assert result.issues[0].code == "unsupported_scope"
            assert result.scopes[0].expected == 1
    else:
        assert not result.issues and not result.coverage_issues()
        scope = result.scopes[0]
        assert (
            scope.terminal and scope.expected == scope.listed == scope.unique == scope.details == 0
        )
        assert len(scope.evidence) == 3 and session.page.calls == 2
