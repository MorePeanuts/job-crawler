"""Real list/field fragments; synthetic eligibility variants are explicitly marked."""

import json
from datetime import datetime
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest
from bs4 import BeautifulSoup

from job_crawler.adapters.sjm import LANGUAGE, ROOT, SjmPublicJobs, catalog, detail, work_type
from job_crawler.incremental import IncrementalSource
from job_crawler.models import Job, Scope, Source
from job_crawler.transport import CrawlError, Session

PAGES = json.loads((Path(__file__).parent / "fixtures/sjm/pages.json").read_text())
ROWS = {row["id"]: row for n in [1, 2, 3] for row in catalog(PAGES[str(n)], n)[1]}


def detail_page(row: dict[str, str], fresh: bool = False) -> str:
    doc = BeautifulSoup(PAGES["detail-6250"], "html.parser")
    values = doc.select("dd")
    values[0].string = row["title"]
    for idx, field in [(1, "department"), (2, "location")]:
        anchor = values[idx].select_one("a")
        assert anchor is not None
        anchor.string = row[field]
        anchor["href"] = row[field + "_path"]
    values[3].string = datetime.fromisoformat(row["published"]).strftime("%d/%m/%Y")
    values[4].string = (
        "Fresh graduates are welcome. Bachelor degree required."
        if fresh
        else "Bachelor degree; minimum 3 years of relevant experience."
    )
    values[5].string = "Prepare project documentation and maintain quality records."
    anchor = doc.select_one('a[href^="/Jobs/Apply/"]')
    assert anchor is not None
    anchor["href"] = "/Jobs/Apply/" + row["id"]
    return str(doc)


class Replay:
    last_evidence = "initial"

    def __init__(self, fault: str = ""):
        self.fault = fault
        self.page = self
        self.calls: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == LANGUAGE and not ready_endpoints
        self.calls.append(url)

    async def content(self) -> str:
        return PAGES["1"]

    async def request_html(self, url: str) -> str:
        self.calls.append(url)
        self.last_evidence = url
        assert "/Apply/" not in url and "/Account/" not in url
        parts = urlsplit(url)
        if parts.query:
            page = parse_qs(parts.query)["page"][0]
            html = PAGES[page]
            if self.fault == "pagecount" and page == "2":
                html = html.replace('<option value="3">3 Page</option>', "")
            if self.fault == "duplicate" and page == "2":
                doc = BeautifulSoup(html, "html.parser")
                first = doc.select_one(".post")
                assert first is not None
                replacement = BeautifulSoup(PAGES["1"], "html.parser").select_one(".post")
                assert replacement is not None
                first.replace_with(replacement)
                html = str(doc)
            if self.fault == "short" and page == "1":
                doc = BeautifulSoup(html, "html.parser")
                first = doc.select_one(".post")
                assert first is not None
                first.decompose()
                html = str(doc)
            return html
        key = parts.path.split("/")[-1]
        if self.fault == "detail" and key == "6250":
            raise TimeoutError("public detail unavailable")
        return detail_page(ROWS[key], fresh=key == "6250")


def adapter(replay: Replay, now: datetime) -> SjmPublicJobs:
    return SjmPublicJobs(
        Source(
            source_id="COM0492",
            company_id="COM0492",
            company="澳门博彩控股有限公司",
            url=ROOT + "/Jobs",
        ),
        cast(Session, replay),
        now,
    )


async def test_complete_three_pages_with_all_raw_jobs_and_one_synthetic_graduate(
    now: datetime,
) -> None:
    replay = Replay()
    result = await adapter(replay, now).collect()
    assert not result.coverage_issues()
    scope = result.scopes[0]
    assert (scope.expected, scope.listed, scope.unique, scope.details, scope.terminal) == (
        44,
        44,
        44,
        44,
        True,
    )
    assert len(result.jobs) == 44
    assert sum(j.work_type == "校招" for j in result.jobs) == 1
    job = next(j for j in result.jobs if j.source_key == "6250")
    assert job.published == "2026-10-16" and job.location == "Taipa / Cotai"
    assert job.address == job.deadline == job.education == ""
    assert job.company == "澳门博彩控股有限公司"
    assert len(replay.calls) == 48


@pytest.mark.parametrize("fault", ["pagecount", "duplicate", "short", "detail"])
async def test_partial_never_becomes_complete(fault: str, now: datetime) -> None:
    result = await adapter(Replay(fault), now).collect()
    assert result.coverage_issues()
    if fault == "detail":
        assert len(result.jobs) == 43 and result.scopes[0].terminal


@pytest.mark.parametrize(
    ("title", "requirements", "expected"),
    [
        ("Analyst", "Bachelor degree; fresh graduates are welcome.", "校招"),
        ("Graduate Trainee", "Bachelor degree.", "校招"),
        ("Intern", "Fresh graduates are welcome.", "实习"),
        ("Analyst", "Fresh graduates with internship experience preferred.", "校招"),
        ("Executive", "High school graduate or above; minimum 1 year experience.", "未明确校招"),
        ("Analyst", "University degree. Related working experience is an advantage.", "未明确校招"),
        ("Steward", "", "未明确校招"),
    ],
)
def test_explicit_graduate_scope_not_educational_graduation(
    title: str, requirements: str, expected: str
) -> None:
    assert work_type(title, requirements) == expected


def test_unrecognized_campus_wording_requires_review() -> None:
    with pytest.raises(CrawlError):
        work_type("School Leaver Scheme", "Details coming soon")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("SJM Resorts, S.A.", "Another company"),
        ("Browse Job", "瀏覽職位"),
        ('id="searchBar"', 'id="searchBar" value="Analyst"'),
        (
            '<li class="active"><a href="/Jobs?sortedBy=Apply%20Date">All</a></li>',
            '<li class="active"><a href="/Jobs?loc=HK">Hong Kong</a></li>',
        ),
    ],
)
def test_no_partial_filter_or_wrong_language(old: str, new: str) -> None:
    assert old in PAGES["1"]
    with pytest.raises(CrawlError):
        catalog(PAGES["1"].replace(old, new), 1)


def test_real_detail_and_na_do_not_invent_campus_or_qualification() -> None:
    fields = detail(PAGES["detail-6250"], ROWS["6250"])
    assert fields["work_type"] == "未明确校招" and "ETL" in fields["duties"]
    fields = detail(PAGES["detail-6257"], ROWS["6257"])
    assert fields["requirements"] == "" and fields["work_type"] == "未明确校招"


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("/Jobs/Apply/6250", "/Jobs/Apply/999"),
        ("16/10/2026", "15/10/2026"),
        ("/Jobs?dept=DN0022", "/Jobs?dept=DN9999"),
        ("/Jobs?loc=COT", "/Jobs?loc=HK"),
        ("Requirements", "Qualifications"),
        ("Developing ETL", '<img src="/jobs.png">Developing ETL'),
    ],
)
def test_detail_identity_date_and_attachment_failures(old: str, new: str) -> None:
    assert old in PAGES["detail-6250"]
    with pytest.raises(CrawlError):
        detail(PAGES["detail-6250"].replace(old, new), ROWS["6250"])


class Reuse:
    def __init__(self, jobs: list[Job]):
        self.jobs = {j.source_key: j for j in jobs}

    def before_detail(
        self,
        entity: str,
        listing: object,
        scope: Scope,
        evidence: str,
        listing_job: Job | None = None,
    ) -> list[Job] | None:
        assert "/Jobs?page=" in evidence
        scope.reused_details += 1
        return [self.jobs[entity.split(":")[1]]]

    def remember(self, entity: str, listing: object, jobs: list[Job]) -> None:
        raise AssertionError("cached records must not be remembered as fresh")


async def test_incremental_reuse_refreshes_catalog_and_full_collection_reads_details(
    now: datetime,
) -> None:
    full = await adapter(Replay(), now).collect()
    replay = Replay()
    instance = adapter(replay, now)
    instance.incremental = cast(IncrementalSource, Reuse(full.jobs))
    result = await instance.collect()
    assert not result.coverage_issues() and result.scopes[0].reused_details == 44
    assert len(replay.calls) == 4 and len(result.jobs) == 44
