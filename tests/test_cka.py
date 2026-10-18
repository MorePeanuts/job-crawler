"""CK Asset official two-page catalog and inline graduate exception."""

from pathlib import Path
from typing import cast

import pytest
from bs4 import BeautifulSoup

from job_crawler.adapters.cka import ROOT, CkaCareers, catalog, recruitment_type
from job_crawler.models import Source
from job_crawler.transport import Session

FIX = Path(__file__).parent / "fixtures/cka"


class Replay:
    last_evidence = "initial"

    def __init__(self, fault=""):
        self.fault = fault
        self.calls = []

    async def open(self, url, *, ready_endpoints=()):
        assert url == ROOT

    async def request_html(self, url):
        self.calls.append(url)
        assert url in {ROOT, ROOT + "?page=1"}
        page = int("?page=1" in url)
        self.last_evidence = f"page{page}"
        s = (FIX / f"page{page}.html").read_text()
        if page == 0 and self.fault in {"short", "missing_body"}:
            d = BeautifulSoup(s, "html.parser")
            node = d.select_one(".panel-collapse" if self.fault == "missing_body" else ".panel")
            assert node is not None
            node.decompose()
            return str(d)
        if page == 0 and self.fault == "department":
            s = s.replace('value="All"', 'value="47"')
        if page == 0 and self.fault == "foreign":
            s = s.replace('href="?page=1"', 'href="https://other.test/careers?page=1"')
        if page == 0 and self.fault == "no_pager":
            s = s.replace('class="pager"', 'class="changed"')
        if page == 0 and self.fault == "identity":
            s = s.replace("CK Asset Holdings Limited", "Another company")
        if page == 1 and self.fault == "wrong_page":
            s = (FIX / "page0.html").read_text()
        if page == 1 and self.fault == "duplicate_id":
            s = s.replace("accordion-13326-1", "accordion-1305-1")
        if page == 1 and self.fault == "duplicate_ref":
            s = s.replace("Ref.: GLU-LA", "Ref.: NKW-AP")
        if page == 1 and self.fault == "media":
            s = s.replace("Ref.: LFA-SP", 'Ref.: LFA-SP<img src="poster.png">')
        if page == 1 and self.fault == "broken_ref":
            s = s.replace("Ref.: LFA-SP", "missing reference")
        if page == 1 and self.fault == "headings":
            s = s.replace("Requirements:", "Qualifications:")
        if page == 1 and self.fault == "duplicate_body":
            s = s.replace('id="accordion-1338-1"', 'id="accordion-4559-1"')
        return s


def adapter(replay, now):
    return CkaCareers(
        Source(source_id="COM0297", company_id="COM0297", company="长江实业集团有限公司", url=ROOT),
        cast(Session, replay),
        now,
    )


@pytest.mark.asyncio
async def test_two_pages_and_explicit_graduate_exception(now):
    replay = Replay()
    result = await adapter(replay, now).collect()
    assert not result.issues and not result.coverage_issues()
    assert len(result.jobs) == 12
    assert result.scopes[0].expected == 12
    assert replay.calls == [ROOT, ROOT + "?page=1"]
    grads = [j for j in result.jobs if j.work_type == "校招"]
    assert [j.title for j in grads] == ["Sales Professionals"]
    assert (
        grads[0].duties == "" and "no prior full-time experience required" in grads[0].requirements
    )
    assert grads[0].source_url == ROOT + "?page=1#accordion-4559-1"
    assert all(
        not j.published and not j.deadline and not j.location and not j.education
        for j in result.jobs
    )
    assert sum(j.work_type == "临时岗位" for j in result.jobs) == 1
    officer = next(j for j in result.jobs if j.title == "Officer, PI&V")
    assert "property valuation" in officer.duties and "Degree or above" in officer.requirements


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "short",
        "missing_body",
        "department",
        "foreign",
        "no_pager",
        "identity",
        "wrong_page",
        "duplicate_id",
        "duplicate_ref",
        "media",
        "broken_ref",
        "headings",
        "duplicate_body",
    ],
)
async def test_incomplete_catalog_is_not_accepted(now, fault):
    result = await adapter(Replay(fault), now).collect()
    assert result.issues and result.coverage_issues()
    if fault in {
        "wrong_page",
        "duplicate_id",
        "duplicate_ref",
        "media",
        "broken_ref",
        "headings",
        "duplicate_body",
    }:
        assert len(result.jobs) >= 8


def test_actual_first_page_has_no_explicit_graduate_job():
    _, _, rows = catalog((FIX / "page0.html").read_text(), 0)
    assert all(recruitment_type(x["title"], x["requirements"]) == "未明确校招" for x in rows)


def test_temporary_student_role_is_not_formal_campus():
    assert (
        recruitment_type(
            "Temporary Sales Service Assistant",
            "Fresh graduates or students will also be considered",
        )
        == "临时岗位"
    )
    assert (
        recruitment_type("Auditor", "University graduate with at least 3 years experience")
        == "未明确校招"
    )
