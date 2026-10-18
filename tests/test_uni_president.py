"""Inline pagination, MA expansion, dates, and partial scope evidence."""

import json
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest

from job_crawler.adapters.uni_president import (
    API,
    CAREERS,
    EMPLOYERS,
    MA,
    UniPresidentCareers,
    ma_program,
)
from job_crawler.models import Source
from job_crawler.transport import CrawlError, Session

FIX = Path(__file__).parent / "fixtures/uni_president"


class Replay:
    last_evidence = "initial"

    def __init__(self, fault=""):
        self.fault = fault
        self.calls = []

    async def open(self, url, *, ready_endpoints=()):
        assert url == CAREERS and ready_endpoints == (API + "?",)

    async def observed(self, needle):
        assert needle == API + "?"
        return {"body": (FIX / "page1.json").read_text()}

    async def request(self, url, *, credentials):
        assert credentials == "omit" and url.startswith(API + "?")
        q = parse_qs(urlsplit(url).query)
        assert q["countPerPage"] == ["10"]
        self.calls.append(q)
        page = q["page"][0]
        data = json.loads((FIX / f"page{page}.json").read_text())
        if page == "2":
            if self.fault == "request":
                raise TimeoutError("second page unavailable")
            if self.fault == "total":
                data["totalCount"] += 1
            if self.fault == "short":
                data["items"].pop()
            if self.fault == "duplicate":
                data["items"][0]["jobId"] = 5901
        if self.fault == "intro":
            data["items"][1]["jobIntroUrl"] = "https://example.test/new-jobs.pdf"
        if self.fault == "status":
            data["items"][1]["isActiveMark"] = False
        if self.fault == "date":
            data["items"][1]["startDate"] = "2026-10-18"
        if self.fault == "new_plan":
            data["items"][1]["isSubJob"] = True
        self.last_evidence = "page" + page
        return data


class Adapter(UniPresidentCareers):
    async def views(self):
        replay = cast(Replay, self.session)
        values = [
            (FIX / (name + ".html")).read_text()
            for name in ["conditions", "faq", "matching", "intern"]
        ]
        if replay.fault == "faq":
            values[1] = values[1].replace("可以，請您於填寫履歷時說明。", "不可以")
        if replay.fault == "missing_company":
            values[0] = values[0].replace("www.7-11.com.tw", "other.example")
        if replay.fault == "matching":
            values[2] = "<main>新的職缺目錄</main>"
        if replay.fault == "intern":
            values[3] = "<main>正式校招</main>"
        return (*values, ["conditions", "faq", "matching", "intern"])


def make(now, fault=""):
    replay = Replay(fault)
    return Adapter(
        Source(
            source_id="COM0164", company_id="COM0164", company="统一企业股份有限公司", url=CAREERS
        ),
        cast(Session, replay),
        now,
    ), replay


@pytest.mark.asyncio
async def test_complete_two_pages_and_six_company_ma(now):
    adapter, replay = make(now)
    result = await adapter.collect()
    assert not result.coverage_issues(), result.issues
    assert len(result.jobs) == 21 and len({job.key for job in result.jobs}) == 21
    assert [(s.expected, s.unique, s.details, s.skipped_out_of_scope) for s in result.scopes] == [
        (16, 16, 16, 0),
        (6, 6, 6, 0),
        (2, 2, 0, 2),
    ]
    assert [q["page"] for q in replay.calls] == [["1"], ["2"]]
    assert replay.calls[0]["targetDate"] == replay.calls[1]["targetDate"]
    grads = [j for j in result.jobs if j.work_type == "校招"]
    assert len(grads) == 6 and {j.source_key.split(":")[1] for j in grads} == EMPLOYERS
    assert not any(j.source_key == "5901" for j in result.jobs)
    assert len([j for j in grads if j.title == "營銷事業夥伴"]) == 4
    assert all(j.source_url == MA and not j.unit and not j.address for j in grads)
    assert all("我是應屆畢業生" in j.requirements for j in grads)
    assert all(j.published == "2025-12-03" and j.deadline == "2026-11-29T16:00:00Z" for j in grads)
    assert all(j.location == "台灣 (依集團 / 公司指定分發)" for j in grads)
    assert all(j.evidence == ["page1", "conditions", "faq"] for j in grads)
    assert next(j for j in result.jobs if j.source_key == "5921").work_type == "未明确校招"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "request",
        "total",
        "short",
        "duplicate",
        "intro",
        "status",
        "date",
        "new_plan",
        "faq",
        "missing_company",
        "matching",
        "intern",
    ],
)
async def test_changed_or_incomplete_scope_stays_partial(now, fault):
    adapter, _ = make(now, fault)
    result = await adapter.collect()
    assert result.issues and result.coverage_issues()
    if fault in {"request", "total", "short", "duplicate"}:
        assert len(result.jobs) == 9
    if fault in {"faq", "missing_company"}:
        assert len(result.jobs) == 15
    if fault in {"matching", "intern"}:
        assert len(result.jobs) == 21


def test_ma_missing_duties_not_silently_dropped():
    conditions = (FIX / "conditions.html").read_text().replace("工作內容", "未知內容", 1)
    with pytest.raises(CrawlError, match="分节不完整"):
        ma_program(conditions, (FIX / "faq.html").read_text())


@pytest.mark.asyncio
async def test_real_tab_roles_and_question_disclosure(now):
    from bs4 import BeautifulSoup

    from job_crawler.adapters.uni_president import INTERN, MATCHING

    class Element:
        def __init__(self, page, found, target=None):
            assert found, "public DOM element not found"
            self.page = page
            self.target = target
            self.first = self

        async def click(self):
            if self.target:
                self.page.name = self.target

        async def wait_for(self):
            pass

    class Page:
        name = "conditions"

        def soup(self):
            return BeautifulSoup((FIX / (self.name + ".html")).read_text(), "html.parser")

        def get_by_role(self, role, *, name, exact):
            assert exact
            found = [
                e
                for e in self.soup().select("button, [role]")
                if e.get("role", e.name) == role and e.get_text(strip=True) == name
            ]
            return Element(self, found, "conditions" if name == "職缺條件" else "faq")

        def get_by_text(self, value, *, exact):
            assert exact
            return Element(self, self.soup().find(string=lambda s: s and s.strip() == value))

        def locator(self, selector):
            return Element(self, self.soup().select(selector))

        async def content(self):
            return (FIX / (self.name + ".html")).read_text()

    class Views:
        page = Page()

        async def open(self, url):
            self.page.name = {MA: "conditions", MATCHING: "matching", INTERN: "intern"}[url]

        def snapshot(self, label, html):
            assert html
            return label

    adapter = UniPresidentCareers(
        Source(
            source_id="COM0164", company_id="COM0164", company="统一企业股份有限公司", url=CAREERS
        ),
        cast(Session, Views()),
        now,
    )
    conditions, faq, matching, intern, evidence = await adapter.views()
    assert len(ma_program(conditions, faq)[0]) == 6
    assert "進行媒合60天" in matching and "實習期間為全職學生身分" in intern
    assert len(evidence) == 4
