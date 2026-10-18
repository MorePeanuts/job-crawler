"""Public business fragments. Professionals are protocol samples, never live campus jobs."""

import json
from pathlib import Path
from typing import cast

import pytest
from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.pccw import (
    CATEGORIES,
    INVITES,
    PLAN,
    PROGRAMMES,
    ROOT,
    PccwGraduate,
    catalog,
    closed_programme,
    detail,
    home,
    plan,
    programme,
    programme_url,
)
from job_crawler.incremental import IncrementalSource
from job_crawler.models import Job, Scope, Source
from job_crawler.transport import CrawlError, Session

PAGES = json.loads((Path(__file__).parent / "fixtures/pccw/pages.json").read_text())
PRO = ROOT + "/pccw/go/Professionals/4708010/"
ENTRY = ROOT + "/pccw/content/" + PLAN + "?locale=en_US"
TOTAL, ROWS, NEXT = catalog(PAGES["professionals-1"], PRO, 0, "Professionals")


def node(doc: BeautifulSoup, selector: str) -> Tag:
    result = doc.select_one(selector)
    assert result is not None
    return result


class Replay:
    last_evidence = "initial"

    def __init__(self):
        self.pages = PAGES.copy()
        self.calls: list[str] = []
        self.page = self

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == ENTRY and not ready_endpoints
        self.calls.append(url)

    async def request_html(self, url: str) -> str:
        assert "/apply/" not in url and "forms.office" not in url
        self.calls.append(url)
        self.last_evidence = url
        return self.pages[url]


def make(replay: Replay, now) -> PccwGraduate:
    return PccwGraduate(
        Source(source_id="COM0395", company_id="COM0395", company="电讯盈科有限公司", url=ENTRY),
        cast(Session, replay),
        now,
    )


def synthetic_one(tenant: str) -> str:
    """Move one actual professional into a synthetic graduate category for traversal tests."""
    b = BeautifulSoup(PAGES["professionals-1"], "html.parser")
    name = b.select_one("#category-name")
    assert name is not None
    name.string = "Graduate Hiring_" + tenant
    for row in b.select("tr.data-row")[1:]:
        row.decompose()
    for label in b.select(".paginationLabel"):
        label.string = "Results 1 – 1 of 1"
    return str(b)


@pytest.mark.asyncio
async def test_current_complete_zero_and_closed(now):
    replay = Replay()
    result = await make(replay, now).collect()
    assert not result.issues and not result.jobs
    assert not result.coverage_issues()
    assert [(s.expected, s.listed, s.unique, s.skipped_closed) for s in result.scopes] == [
        (12, 12, 12, 12),
        (0, 0, 0, 0),
        (0, 0, 0, 0),
    ]
    assert len([u for u in replay.calls if "Stream---" in u]) == 24
    assert len([u for u in replay.calls if "/job-invite/" in u]) == 2


def test_actual_professional_pagination_and_detail():
    assert TOTAL == 28 and len(ROWS) == 20
    total, rows, end = catalog(PAGES["professionals-2"], NEXT, 20, "Professionals")
    assert total == 28 and len(rows) == 8 and not end
    assert len({r["id"] for r in ROWS + rows}) == 28
    data = detail(PAGES["open-detail"], ROWS[0])
    assert data["published"] == "2026-10-15T23:00:00+08:00"
    assert "10 years" in data["requirements"]
    assert "Requirements" not in data["duties"]
    assert data["unit"] == "PCCW Solutions"


@pytest.mark.parametrize("fault", ["count", "short", "filter", "title", "next"])
def test_catalog_contract_failures(fault):
    b = BeautifulSoup(PAGES["professionals-1"], "html.parser")
    if fault == "count":
        for x in b.select(".paginationLabel"):
            x.string = "Results 1 – 19 of 28"
    elif fault == "short":
        b.select("tr.data-row")[-1].decompose()
    elif fault == "filter":
        node(b, 'input[name="q"]')["value"] = "partial"
    elif fault == "title":
        node(b, "a.jobTitle-link").string = "Wrong title"
    else:
        for a in b.select('a[title="Page 2"]'):
            a["href"] = str(a["href"]).replace("/20/", "/40/")
    with pytest.raises(CrawlError):
        catalog(str(b), PRO, 0, "Professionals")


@pytest.mark.parametrize("fault", ["missing", "recommended", "identity"])
def test_empty_must_be_explicit(fault):
    u = ROOT + "/pccw/go/" + CATEGORIES["pccw"]
    html = PAGES[u]
    if fault == "missing":
        html = html.replace("There are currently no open positions", "Loading positions")
    elif fault == "recommended":
        html = html.replace("The 0 most recent", "The 2 most recent")
    else:
        html = html.replace("Graduate Hiring_pccw", "Professionals")
    with pytest.raises(CrawlError):
        catalog(html, u, 0, "Graduate Hiring_pccw")


@pytest.mark.parametrize("fault", ["id", "date", "location", "requirements", "attachment"])
def test_detail_mismatch(fault):
    b = BeautifulSoup(PAGES["open-detail"], "html.parser")
    if fault == "id":
        node(b, 'link[rel="canonical"]')["href"] = ROWS[1]["url"]
    elif fault == "date":
        node(b, 'meta[itemprop="datePosted"]')["content"] = "Fri Oct 16 15:00:00 UTC 2026"
    elif fault == "location":
        node(b, '[data-careersite-propertyid="location"]').string = "Wrong location"
    elif fault == "requirements":
        for x in b.select("strong"):
            if x.get_text(strip=True) == "Requirements":
                x.string = "Unverified qualifications"
    else:
        node(b, ".jobdescription").append(b.new_tag("img", src="poster.png"))
    with pytest.raises(CrawlError):
        detail(str(b), ROWS[0])


@pytest.mark.parametrize("fault", ["menu", "invite", "body", "contact"])
def test_programme_changes_fail(fault):
    key = "Information-Technology"
    u = programme_url("pccw", "Technology", key)
    html = PAGES[u]
    if fault == "menu":
        html = html.replace(
            "Technology-Stream---Engineering/", "Technology-Stream---New-Programme/"
        )
    elif fault == "invite":
        html = html.replace("job-invite/58548", "job-invite/58549")
    elif fault == "body":
        html = html.replace("We are looking for", "New qualifications")
    else:
        html = html.replace("2024 has closed", "2027 is open")
    with pytest.raises(CrawlError):
        programme(html, "pccw", "Technology", key)


def test_root_navigation_changes_fail():
    with pytest.raises(CrawlError):
        home(PAGES[ROOT + "/pccw/"].replace("7939210", "999"), "pccw")
    with pytest.raises(CrawlError):
        plan(PAGES[ENTRY].replace("Business-Stream---Digital-Ventures", "New-Stream"), "pccw")


@pytest.mark.asyncio
async def test_programme_open_is_not_zero_success(now):
    replay = Replay()
    u = ROOT + "/job-invite/58548/"
    replay.pages[u] = replay.pages[u].replace("Sorry, this position has been filled.", "Apply now")
    result = await make(replay, now).collect()
    assert result.coverage_issues()
    assert any(i.code == "unsupported_scope" for i in result.issues)
    assert not result.jobs
    assert result.scopes[0].skipped_closed == 0
    assert all(s.terminal for s in result.scopes[1:])


@pytest.mark.asyncio
async def test_synthetic_open_catalog_duplicate_portals_and_reuse(now):
    replay = Replay()
    for tenant in CATEGORIES:
        replay.pages[ROOT + "/" + tenant + "/go/" + CATEGORIES[tenant]] = synthetic_one(tenant)
    replay.pages[ROWS[0]["url"]] = PAGES["open-detail"]
    result = await make(replay, now).collect()
    assert not result.issues and not result.coverage_issues()
    assert len(result.jobs) == 1  # One posting ID across both portals.
    assert [s.details for s in result.scopes[1:]] == [1, 1]

    class Reuse:
        def before_detail(
            self, entity: str, listing: object, scope: Scope, evidence: str, listing_job: Job | None
        ):
            scope.reused_details += 1
            return [result.jobs[0].model_copy(deep=True)]

    replay.calls.clear()
    instance = make(replay, now)
    instance.incremental = cast(IncrementalSource, Reuse())
    again = await instance.collect()
    assert not again.issues and len(again.jobs) == 1
    assert ROWS[0]["url"] not in replay.calls
    assert [s.reused_details for s in again.scopes[1:]] == [1, 1]
    assert len([u for u in replay.calls if "Stream---" in u]) == 24


@pytest.mark.asyncio
async def test_partial_project_retains_other_scopes(now):
    replay = Replay()
    del replay.pages[programme_url("hkt", "Business", "Media")]
    result = await make(replay, now).collect()
    assert result.issues and result.coverage_issues()
    assert result.scopes[0].skipped_closed == 0
    assert all(s.terminal for s in result.scopes[1:])


def test_closed_announcement_identity():
    u = ROOT + "/job-invite/58548/"
    with pytest.raises(CrawlError):
        closed_programme(PAGES[u], "Business")
    for stream, (invite, _) in INVITES.items():
        closed_programme(PAGES[ROOT + "/job-invite/" + invite + "/"], stream)
    assert sum(map(len, PROGRAMMES.values())) == 12


@pytest.mark.asyncio
async def test_duplicate_catalog_ids_not_complete(now):
    replay = Replay()
    u = ROOT + "/pccw/go/" + CATEGORIES["pccw"]
    b = BeautifulSoup(synthetic_one("pccw"), "html.parser")
    row = b.select_one("tr.data-row")
    assert row is not None
    node(b, "tbody").append(BeautifulSoup(str(row), "html.parser"))
    for label in b.select(".paginationLabel"):
        label.string = "Results 1 – 2 of 2"
    replay.pages[u] = str(b)
    result = await make(replay, now).collect()
    assert result.coverage_issues()
    assert any(i.code == "duplicate_page" for i in result.issues)
    assert result.scopes[-1].terminal


@pytest.mark.asyncio
async def test_one_portal_detail_failure_is_not_complete(now):
    replay = Replay()
    replay.pages[ROOT + "/pccw/go/" + CATEGORIES["pccw"]] = synthetic_one("pccw")
    result = await make(replay, now).collect()
    assert result.coverage_issues() and not result.jobs
    assert result.scopes[1].listed == 1 and result.scopes[1].details == 0
    assert result.scopes[-1].terminal
