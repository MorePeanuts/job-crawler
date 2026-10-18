"""Real public markup with shortened synthetic programme narratives; no live credentials."""

import json
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest
from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.mtr import ENTRY, MtrGraduate, campaign, programme_fields
from job_crawler.incremental import IncrementalSource
from job_crawler.models import Job, Scope, Source
from job_crawler.transport import Session

PAGES = json.loads((Path(__file__).parent / "fixtures/mtr/pages.json").read_text())
NOTICE = "https://careers.mtr.com.hk/careersection/mtr_graduates_apply/jobdetail.ftl?job=260000UY&lang=en"


def element(document: Tag, selector: str) -> Tag:
    node = document.select_one(selector)
    assert node is not None
    return node


class Replay:
    last_evidence = "initial"

    def __init__(self, homepage: str = "", notice: str = "", fail: bool = False):
        self.page = self
        self.homepage = homepage or PAGES["campaign"]
        self.notice = notice or PAGES["announcement"]
        self.fail = fail
        self.url = ""
        self.opened: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url in {ENTRY, NOTICE} and not ready_endpoints
        self.opened.append(url)
        self.url = url
        if self.fail and url == NOTICE:
            raise TimeoutError("public announcement unavailable")

    async def content(self) -> str:
        return self.homepage if self.url == ENTRY else self.notice

    def snapshot(self, label: str, html: str) -> str:
        self.last_evidence = label
        return label


def adapter(replay: Replay, now: datetime) -> MtrGraduate:
    return MtrGraduate(
        Source(source_id="COM0310", company_id="COM0310", company="香港铁路有限公司", url=ENTRY),
        cast(Session, replay),
        now,
    )


async def test_eight_programmes_reconcile_notice_dates_and_missing_fields(now: datetime) -> None:
    replay = Replay()
    result = await adapter(replay, now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 8
    assert replay.opened == [ENTRY, NOTICE]
    assert [(s.expected, s.details, s.terminal) for s in result.scopes] == [
        (1, 1, True),
        (8, 8, True),
    ]
    assert len({job.source_key for job in result.jobs}) == 8
    for job in result.jobs:
        assert job.source_key.startswith("260000UY:modal")
        assert job.company == "香港铁路有限公司" and job.batch == "2027 Graduate Recruitment"
        assert job.apply_url == NOTICE
        assert job.published == "2026-09-15 09:03:18+08:00"  # Not the 09:00 application start.
        assert job.deadline == "2026-10-27 23:59:00+08:00"  # Not the Oct 23/24 maintenance.
        assert job.location == job.address == job.education == ""
        assert "not more than 3 years' work experience" in job.requirements
        assert "final-year university students and recent graduates" in job.requirements
        assert "Structured programme training" in job.duties
        assert "We are looking for" not in job.duties
        assert job.evidence == ["mtr-graduate-campaign", "mtr-graduate-announcement"]


@pytest.mark.parametrize(
    "fault",
    ["count", "duplicate_target", "missing_modal", "extra_modal", "foreign_notice", "missing_faq"],
)
async def test_directory_or_public_scope_changes_never_become_complete(
    fault: str, now: datetime
) -> None:
    document = BeautifulSoup(PAGES["campaign"], "html.parser")
    if fault == "count":
        html = str(document).replace(
            "8 different programmes available", "9 different programmes available"
        )
    else:
        if fault == "duplicate_target":
            element(document, '[data-bs-target="#modal2"]')["data-bs-target"] = "#modal1"
        if fault == "missing_modal":
            element(document, "#modal8").decompose()
        if fault == "extra_modal":
            document.append(
                BeautifulSoup('<div class="opportunities-modal" id="modal99"></div>', "html.parser")
            )
        if fault == "foreign_notice":
            element(document, "#sectionApplication a")["href"] = "https://other.example/job"
        if fault == "missing_faq":
            element(document, "#sectionFAQs").decompose()
        html = str(document)
    result = await adapter(Replay(homepage=html), now).collect()
    assert result.coverage_issues() and not result.jobs


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("260000UY", "260000XX"),
        ("2027 Graduate Recruitment", "2026 Graduate Recruitment"),
        ("Full-time", "Part-time"),
        (">Graduates<", ">Experienced<"),
        ("27/Oct/26, 11:59:00 PM", "26/Oct/26, 11:59:00 PM"),
        ("Human Resources Associate Programme", "Different Programme"),
        ("final-year university students and recent graduates", "experienced professionals"),
        (ENTRY, "https://other.example/campaign"),
    ],
)
async def test_announcement_must_match_identity_dates_and_programme_set(
    old: str, new: str, now: datetime
) -> None:
    assert old in PAGES["announcement"]
    result = await adapter(Replay(notice=PAGES["announcement"].replace(old, new)), now).collect()
    assert result.coverage_issues() and not result.jobs


async def test_network_failure_cannot_become_zero(now: datetime) -> None:
    result = await adapter(Replay(fail=True), now).collect()
    assert result.coverage_issues() and not result.jobs


@pytest.mark.parametrize(
    "fault", ["wrong_title", "attachment", "missing_qualification", "duplicate_qualification"]
)
async def test_one_bad_programme_preserves_other_seven(fault: str, now: datetime) -> None:
    document = BeautifulSoup(PAGES["campaign"], "html.parser")
    body = element(document, "#modal8 .modal-body")
    if fault == "wrong_title":
        element(body, "h3").string = "Functional Professional Expertise - Different Programme"
    if fault == "attachment":
        body.append(BeautifulSoup('<img src="requirements.png">', "html.parser"))
    if fault == "missing_qualification":
        next(p for p in body.select("p") if p.get_text() == "We are looking for:").decompose()
    if fault == "duplicate_qualification":
        body.append(BeautifulSoup("<p>We are looking for:</p>", "html.parser"))
    result = await adapter(Replay(homepage=str(document)), now).collect()
    assert len(result.jobs) == 7 and result.coverage_issues()
    assert result.scopes[1].details == 7 and result.scopes[1].terminal
    assert any(issue.job_key == "260000UY:modal8" for issue in result.issues)


def test_actual_title_punctuation_aliases_and_qualification_split() -> None:
    project = campaign(PAGES["campaign"])
    programme = next(p for p in project.programmes if p.key == "modal9")
    category, duties, requirements = programme_fields(programme)
    assert category == "Functional Professional Expertise"
    assert duties == "Structured programme training and practical work."
    assert "Final year university students" in requirements


async def test_incremental_still_verifies_whole_campaign_and_public_notice(now: datetime) -> None:
    class Reuse:
        def before_detail(
            self,
            entity: str,
            listing: object,
            scope: Scope,
            evidence: str,
            listing_job: Job | None = None,
        ) -> list[Job]:
            assert isinstance(listing, dict) and listing["published"] == "2026-09-15 09:03:18+08:00"
            assert listing_job is not None and evidence == "mtr-graduate-campaign"
            scope.reused_details += 1
            return [listing_job]

    replay = Replay()
    instance = adapter(replay, now)
    instance.incremental = cast(IncrementalSource, Reuse())
    result = await instance.collect()
    assert not result.coverage_issues() and result.scopes[1].reused_details == 8
    assert replay.opened == [ENTRY, NOTICE]
