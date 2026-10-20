"""中电控股官网毕业生项目与 Oracle 详情身份回放。"""

import json
from datetime import datetime
from typing import Any, cast

import pytest

from job_crawler.adapters.clp import APPLY_URL, ClpGraduate2027
from job_crawler.models import Source
from job_crawler.transport import Session

ORACLE_JOB = "https://iabhtj.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CLP-Recruitment-System/job/1125"
DETAIL_URL = "https://iabhtj.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?finder=ById;Id=%221125%22,siteNumber=CX_1"
HTML = '<footer>© CLP Holdings Limited</footer><h1>CLP Engineering Graduate Trainee Programme 2027</h1><p>final-year student</p><p>Application Deadline: 6 December 2026</p><a href="https://e.clp.com.hk/gt2027">Apply Now</a>'


class Page:
    url = ""

    def __init__(self, html: str):
        self.html = html

    async def content(self) -> str:
        return self.html


class Replay:
    def __init__(self, *, html: str = HTML, row: dict[str, Any] | None = None):
        self.page = Page(html)
        self.last_evidence = "replay.json"
        self.opens: list[str] = []
        self.row = row or {
            "Id": "1125",
            "Title": "CLP Engineering Graduate Trainee Programme 2027",
            "RequisitionType": "Programme",
            "JobSchedule": "Full time",
            "LegalEmployerId": 300000005637185,
            "PrimaryLocationCountry": "HK",
            "PrimaryLocation": "Hong Kong",
            "ApplyWhenNotPostedFlag": False,
            "ExternalPostedStartDate": "2026-09-15T01:33:19+00:00",
            "ExternalPostedEndDate": "2026-12-06T15:55:00+00:00",
            "ExternalDescriptionStr": "<p>Programme work and rotation.</p><p>Who are we looking for?</p><p>Bachelor's degree or above in Electrical Engineering.</p><p>Remarks:</p><p>Apply online.</p>",
            "Category": "Engineering",
        }

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.opens.append(url)
        self.page.url = ORACLE_JOB if url == APPLY_URL else url

    async def observed(self, needle: str) -> dict[str, Any]:
        assert "recruitingCEJobRequisitionDetails" in needle
        return {"url": DETAIL_URL, "body": json.dumps({"items": [self.row], "count": 1})}


def adapter(replay: Replay) -> ClpGraduate2027:
    source = Source(
        source_id="COM0228",
        company_id="COM0228",
        company="中电控股有限公司",
        url="https://www.clpgroup.com/en/careers/working-at-clp/graduate-trainee.html",
    )
    return ClpGraduate2027(source, cast(Session, replay), datetime(2026, 10, 20))


@pytest.mark.asyncio
async def test_programme_and_oracle_detail_are_linked() -> None:
    replay = Replay()
    result = await adapter(replay).collect()
    assert not result.coverage_issues()
    assert replay.opens[-1] == APPLY_URL
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.source_key == "1125"
    assert job.published == "2026-09-15T01:33:19+00:00"
    assert job.deadline == "2026-12-06T15:55:00+00:00"
    assert "Bachelor's degree" in job.requirements
    assert "Apply online" not in job.requirements


@pytest.mark.asyncio
async def test_wrong_apply_link_or_legal_employer_fails_closed() -> None:
    bad_link = await adapter(
        Replay(html=HTML.replace(APPLY_URL, "https://example.com/jobs"))
    ).collect()
    assert bad_link.coverage_issues() and not bad_link.jobs
    row = Replay().row
    row["LegalEmployerId"] = 42
    bad_employer = await adapter(Replay(row=row)).collect()
    assert bad_employer.coverage_issues() and not bad_employer.jobs


@pytest.mark.asyncio
async def test_mismatched_date_and_missing_qualification_fail_closed() -> None:
    row = Replay().row
    row["ExternalPostedEndDate"] = "2026-12-07T15:55:00+00:00"
    bad_date = await adapter(Replay(row=row)).collect()
    assert bad_date.coverage_issues() and not bad_date.jobs
    row = Replay().row
    row["ExternalDescriptionStr"] = "<p>Programme description only.</p>"
    missing = await adapter(Replay(row=row)).collect()
    assert missing.coverage_issues() and not missing.jobs
