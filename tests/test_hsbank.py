"""Explicit zero counts, correct campus branch and normal UI confirmation."""

import copy
from typing import Any, cast
from urllib.parse import urlencode

import pytest

from job_crawler.adapters.hsbank import (
    CHANNEL,
    CHANNEL_FORM,
    EMPTY,
    ENTRY,
    LIST,
    LIST_FORM,
    ROOT,
    HsbankCampus,
    channel,
    empty_dom,
    empty_list,
    observed_forms,
)
from job_crawler.models import Source
from job_crawler.transport import CrawlError, Session

META: dict[str, Any] = {
    "errCode": 0,
    "data": {
        "name": "校园招聘",
        "code": "xyzp60682",
        "children": [],
        "ref": False,
        "outLink": False,
        "innerLink": False,
        "homeUrl": "#",
        "listUrl": "#",
    },
}
ZERO: dict[str, Any] = {
    "errCode": 0,
    "data": {"pageSize": 5, "currentPage": 1, "pageCount": 1, "rowCount": 0, "data": []},
}
HTML = '<footer>版权所有徽商银行</footer><div id="xyzp"><div class="entirety-headline">校园招聘</div><div class="noList">暂无最新招聘公告</div></div>'


class Replay:
    last_evidence = "page"

    def __init__(self, output=None, fault=""):
        self.output = output
        self.fault = fault
        self.page = self
        self.first = self
        self.responses: list[dict[str, Any]] = [
            {"url": ROOT + p, "post_data": urlencode(f), "status": 200}
            for p, f in [(CHANNEL, CHANNEL_FORM), (LIST, LIST_FORM)]
        ]
        self.clicked = False
        self.requests = []
        self.label = ""

    async def open(self, url, *, ready_endpoints):
        assert url == ENTRY and ready_endpoints == (CHANNEL, LIST)

    async def observed_path(self, path):
        return next(x for x in self.responses if x["url"] == ROOT + path)

    async def content(self):
        return HTML

    async def request(self, url, *, form):
        self.requests.append((url, form))
        if self.fault == "request":
            raise TimeoutError("unavailable")
        data = copy.deepcopy(META if url == ROOT + CHANNEL else ZERO)
        if self.fault == "nonzero" and url == ROOT + LIST:
            data["data"]["rowCount"] = 1
        return data

    def get_by_text(self, label, *, exact):
        assert exact
        self.label = label
        return self

    async def click(self, **options):
        assert options == {"timeout": 10000}
        assert self.label == "校园招聘"
        self.clicked = True

    async def wait_for(self, *, state, **options):
        assert options == {"timeout": 10000}
        assert self.clicked and self.label == EMPTY and state == "visible"
        if self.fault == "ui":
            raise TimeoutError("not visible")

    def snapshot(self, label, html):
        self.last_evidence = label
        return label


async def test_current_zero_requires_api_and_campus_ui(now, tmp_path):
    replay = Replay(tmp_path)
    source = Source(source_id="COM0244", company_id="COM0244", company="徽商银行", url=ENTRY)
    result = await HsbankCampus(source, cast(Session, replay), now).collect()
    assert not result.coverage_issues() and not result.jobs and replay.clicked
    assert replay.requests == [(ROOT + CHANNEL, CHANNEL_FORM), (ROOT + LIST, LIST_FORM)]
    assert result.scopes[0].expected == result.scopes[0].unique == 0


@pytest.mark.parametrize("fault", ["request", "nonzero", "ui"])
async def test_partial_not_zero(now, fault):
    source = Source(source_id="COM0244", company_id="COM0244", company="徽商银行", url=ENTRY)
    result = await HsbankCampus(source, cast(Session, Replay(fault=fault)), now).collect()
    assert result.coverage_issues()


@pytest.mark.parametrize(
    "field,value",
    [
        ("rowCount", 1),
        ("rowCount", False),
        ("currentPage", 2),
        ("pageCount", 0),
        ("data", [{"id": 1}]),
        ("nextPage", 2),
    ],
)
def test_contradictory_or_nonzero_counts(field, value):
    data = copy.deepcopy(ZERO)
    data["data"][field] = value
    with pytest.raises(CrawlError):
        empty_list(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "社会招聘"),
        ("code", "shzp60032"),
        ("children", [{"code": "new"}]),
        ("outLink", True),
        ("homeUrl", "/new"),
    ],
)
def test_changed_channel_tree(field, value):
    data = copy.deepcopy(META)
    data["data"][field] = value
    with pytest.raises(CrawlError):
        channel(data)


def test_dom_empty_in_wrong_branch_cannot_count():
    with pytest.raises(CrawlError):
        empty_dom(HTML.replace('id="xyzp"', 'id="sxszp"'))
    with pytest.raises(CrawlError):
        empty_dom(HTML.replace("暂无最新招聘公告", "加载失败"))


def test_filter_or_other_channel_is_not_unfiltered_campus():
    replay = Replay()
    observed_forms(replay.responses)
    replay.responses[1]["post_data"] += "&keyword=engineer"
    with pytest.raises(CrawlError):
        observed_forms(replay.responses)
