"""Replay public empty scopes; refuse changed or nonzero campus contracts."""

import json
from datetime import datetime
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest

from job_crawler.adapters.gemdale import (
    INTRO_NAMES,
    PLANS,
    ROOT,
    GemdaleCampus,
    empty_catalog,
    empty_introduction,
    search_url,
)
from job_crawler.models import Scope, Source
from job_crawler.transport import CrawlError, Session

PAGES = json.loads((Path(__file__).parent / "fixtures/gemdale/pages.json").read_text())


class Replay:
    last_evidence = "initial"

    def __init__(self, fault: str = ""):
        self.fault = fault
        self.page = self
        self.url = ""
        self.opened: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url.startswith(ROOT + "/") and not ready_endpoints
        assert "/Portal/" not in url and "/social" not in url
        self.url = url
        self.opened.append(url)
        if self.fault == "network" and "3%5E30" in url:
            raise TimeoutError("bounded read failed")

    def snapshot(self, label: str, html: str) -> str:
        self.last_evidence = label
        return label

    async def content(self) -> str:
        parts = urlsplit(self.url)
        query = parse_qs(parts.query)
        key = parts.path.lstrip("/")
        if key == "campus":
            key = query.get("p", ["root"])[0].split("^")[-1]
            if key == "-1":
                key = "all"
        html = PAGES[key]
        if self.fault == "new_job" and key == "31":
            html = html.replace(
                '<li><div class="zwlbm">', '<li class="job-li" jobadid="123"><div class="zwlbm">'
            )
        if self.fault == "new_intro" and key == "hhjh":
            html = html.replace("To be continue", "新增校园招聘公告")
        return html


def adapter(replay: Replay, now: datetime) -> GemdaleCampus:
    return GemdaleCampus(
        Source(
            source_id="COM0401",
            company_id="COM0401",
            company="金地（集团）股份有限公司",
            url=ROOT + "/campus",
        ),
        cast(Session, replay),
        now,
    )


async def test_all_five_directories_and_four_introductions_are_required(now: datetime) -> None:
    replay = Replay()
    result = await adapter(replay, now).collect()
    assert not result.coverage_issues() and not result.jobs
    assert len(result.scopes) == 9 and len(replay.opened) == 10
    assert all(
        (s.expected, s.unique, s.details, s.terminal) == (0, 0, 0, True) for s in result.scopes
    )
    assert {search_url(cat) for cat in ["-1", *PLANS]} <= set(replay.opened)
    assert all(ROOT + "/" + path + "#zw" in replay.opened for path in INTRO_NAMES)


@pytest.mark.parametrize("fault", ["network", "new_job", "new_intro"])
async def test_partial_failures_preserve_other_verified_scopes(fault: str, now: datetime) -> None:
    result = await adapter(Replay(fault), now).collect()
    assert result.coverage_issues() and not result.jobs
    assert len(result.scopes) == 9 and sum(s.terminal for s in result.scopes) == 8
    if fault == "new_job":
        assert result.scopes[1].listed == result.scopes[1].unique == 1
        assert result.issues[0].code == "unsupported_scope"


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("金地（集团）股份有限公司 版权所有", "其他企业 版权所有"),
        ('class="now" href="/campus"', 'class="now" href="/social"'),
        (
            'class="categoryConditions act" datavalue="3^-1"',
            'class="categoryConditions act" datavalue="3^31"',
        ),
        (
            'class="categoryConditions1 act" datavalue=""',
            'class="categoryConditions1 act" datavalue="工程"',
        ),
        ('id="ss" type="hidden" value="2"', 'id="ss" type="hidden" value="1"'),
        ('id="k" placeholder', 'id="k" value="工程" placeholder'),
        ("抱歉!暂无在招职位", "加载中"),
        ("抱歉!暂无在招职位", ""),
        ('href="/jyjh#zw"', 'href="/new-plan#zw"'),
        ('datavalue="3^28"', 'datavalue="3^99"'),
    ],
)
def test_invalid_empty_evidence_is_rejected(old: str, new: str) -> None:
    assert old in PAGES["root"]
    with pytest.raises(CrawlError):
        empty_catalog(PAGES["root"].replace(old, new), "-1", Scope(name="test"))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("To be continue", "现招聘储备干部"),
        ("img6b9.png", "new-jobs.png"),
        ("To be continue", '<a href="/newjobs">新岗位</a>'),
        ("To be continue", '<iframe src="/newjobs"></iframe>'),
    ],
)
def test_changed_plan_content_requires_scope_research(old: str, new: str) -> None:
    assert old in PAGES["jyjh"]
    with pytest.raises(CrawlError):
        empty_introduction(PAGES["jyjh"].replace(old, new), "jyjh")


async def test_every_run_refreshes_empty_scopes_and_rejects_filtered_entry(now: datetime) -> None:
    replay = Replay()
    for _ in range(2):
        assert not (await adapter(replay, now).collect()).coverage_issues()
    assert len(replay.opened) == 20
    instance = adapter(replay, now)
    instance.source.url = search_url("31")
    assert (await instance.collect()).issues[0].code == "entry_mismatch"
    assert len(replay.opened) == 20
