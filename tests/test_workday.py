"""Workday total=0 subsequent pages and missing descriptions must not hide gaps."""

import copy
import json
from pathlib import Path
from typing import cast

import pytest

from job_crawler.adapters.workday import BASE_QUERY, MelcoWorkday, recruitment_type
from job_crawler.incremental import IncrementalSource
from job_crawler.models import Source
from job_crawler.transport import Session

FIX = Path(__file__).parent / "fixtures/workday"
SAMPLES = {
    name: json.loads((FIX / f"{name}.json").read_text()) for name in ["graduate", "intern", "empty"]
}


class Replay:
    last_evidence = "entry"

    def __init__(self, fault=""):
        self.fault = fault
        self.calls = []
        self.rows = []
        self.details = {}
        for n in range(42):
            sample = copy.deepcopy(SAMPLES["graduate"])
            slug = f"Example_REQ{n}"
            row = sample["listing"]
            row.update(
                title=f"Example {n}", externalPath="/job/Location/" + slug, bulletFields=[f"REQ{n}"]
            )
            info = sample["detail"]["jobPostingInfo"]
            info.update(
                title=row["title"],
                jobPostingId=slug,
                jobReqId=f"REQ{n}",
                externalUrl=f"https://{MelcoWorkday.host}/career" + row["externalPath"],
            )
            self.rows.append(row)
            self.details[slug] = sample["detail"]

    async def open(self, url, *, ready_endpoints=()):
        assert url == f"https://{MelcoWorkday.host}/en-US/career"
        assert ready_endpoints == MelcoWorkday.ready_endpoints

    async def observed(self, endpoint):
        query = {**BASE_QUERY, "searchText": "filtered"} if self.fault == "filter" else BASE_QUERY
        return {"url": endpoint, "post_data": json.dumps(query)}

    async def request(self, url, *, payload=None):
        self.calls.append((url, copy.deepcopy(payload)))
        self.last_evidence = f"list-{payload['offset']}" if payload else url
        if url.endswith("/jobs"):
            assert payload is not None
            offset = payload["offset"]
            assert offset in [0, 20, 40], (
                "must never request out-of-range page which resets to first"
            )
            rows = copy.deepcopy(self.rows[offset : offset + 20])
            total = 42 if offset == 0 else 0
            if self.fault == "zero" and offset == 0:
                total, rows = 0, []
            if self.fault == "short" and offset == 20:
                rows.pop()
            if self.fault == "duplicate" and offset == 20:
                rows[0] = self.rows[0]
            if self.fault == "total" and offset == 20:
                total = 43
            if self.fault == "refresh" and offset == 0 and len(self.calls) > 1:
                rows.reverse()
            return {"total": total, "jobPostings": rows}
        key = url.rsplit("/", 1)[-1]
        d = copy.deepcopy(self.details[key])
        i = d["jobPostingInfo"]
        if key == "Example_REQ21":
            if self.fault in {
                "title",
                "jobReqId",
                "jobPostingId",
                "jobPostingSiteId",
                "externalUrl",
            }:
                i[self.fault] = "wrong"
            if self.fault == "empty":
                i["jobDescription"] = "<p>REQ21 Example</p>"
            if self.fault == "media":
                i["jobDescription"] += '<img src="requirements.png">'
            if self.fault == "date":
                i["startDate"] = "2026-02-30"
            if self.fault == "closed":
                i["canApply"] = False
            if self.fault == "missing_state":
                del i["posted"]
        return d


def adapter(replay, now):
    return MelcoWorkday(
        Source(
            source_id="COM0396",
            company_id="COM0396",
            company="新濠国际发展有限公司",
            url=f"https://{MelcoWorkday.host}/en-US/career",
        ),
        cast(Session, replay),
        now,
    )


@pytest.mark.asyncio
async def test_complete_catalog_uses_first_total_not_empty_termination(now):
    r = Replay()
    result = await adapter(r, now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].details == 42
    assert [p["offset"] for _, p in r.calls if p] == [0, 20, 40, 0]
    assert len(result.jobs) == 42
    job = result.jobs[21]
    assert job.published == "2026-08-16" and job.deadline == "2026-10-19"
    assert job.work_type == "校招"
    assert "2 years working experience" in job.requirements
    assert "Fresh graduate is welcomed" in job.requirements
    assert job.evidence[0] == "list-20"
    assert not job.education and not job.address and not job.unit


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "zero",
        "filter",
        "short",
        "duplicate",
        "total",
        "refresh",
        "title",
        "jobReqId",
        "jobPostingId",
        "jobPostingSiteId",
        "externalUrl",
        "empty",
        "media",
        "date",
        "missing_state",
    ],
)
async def test_failures_keep_gaps_visible_and_successes_preserved(now, fault):
    result = await adapter(Replay(fault), now).collect()
    assert result.issues and result.coverage_issues()
    if fault in {
        "title",
        "jobReqId",
        "jobPostingId",
        "jobPostingSiteId",
        "externalUrl",
        "empty",
        "media",
        "date",
        "missing_state",
    }:
        assert result.scopes[0].terminal and len(result.jobs) == 41
        assert result.issues[0].job_key == "Example_REQ21"
    elif fault not in {"zero", "filter"}:
        assert len(result.jobs) >= 20


@pytest.mark.asyncio
async def test_closed_detail_is_preserved_and_not_a_failed_request(now):
    result = await adapter(Replay("closed"), now).collect()
    assert not result.coverage_issues() and result.jobs[21].closed


def test_real_minimal_samples_and_no_invented_campus(now):
    a = adapter(Replay(), now)
    for name, kind in [("graduate", "校招"), ("intern", "实习")]:
        sample = SAMPLES[name]
        fields = a.parse_detail(sample["detail"], sample["listing"])
        assert fields["work_type"] == kind
    with pytest.raises(Exception, match="正文空白"):
        a.parse_detail(SAMPLES["empty"]["detail"], SAMPLES["empty"]["listing"])
    assert (
        recruitment_type("Trainee Dealer", "No previous experience required", "Full time")
        == "未明确校招"
    )
    assert (
        recruitment_type("Analyst", "University graduate. No prior experience needed.", "Full time")
        == "未明确校招"
    )
    assert recruitment_type("Analyst", "Fresh graduates welcome.", "Part time") == "临时岗位"


class Reuse:
    def __init__(self, jobs):
        self.jobs = {j.source_key: j for j in jobs}

    def before_detail(self, entity, listing, scope, evidence, listing_job=None):
        assert evidence.startswith("list-") and listing_job is None
        scope.reused_details += 1
        return [self.jobs[entity.removeprefix("job:")]]

    def remember(self, entity, listing, jobs):
        raise AssertionError("do not remember reused jobs")


@pytest.mark.asyncio
async def test_incremental_reuses_only_after_refreshing_full_listing(now):
    full = await adapter(Replay(), now).collect()
    r = Replay()
    a = adapter(r, now)
    a.incremental = cast(IncrementalSource, Reuse(full.jobs))
    result = await a.collect()
    assert not result.coverage_issues()
    assert result.scopes[0].reused_details == 42 and len(r.calls) == 4


@pytest.mark.parametrize(
    "name,kind",
    [
        ("consultant", "校招"),
        ("contract", "校招"),
        ("registration", "已录用者登记"),
        ("intern", "实习"),
    ],
)
def test_fwd_real_tenant_samples(now, name, kind):
    from job_crawler.adapters.workday import FwdWorkday

    sample = json.loads((FIX / f"fwd-{name}.json").read_text())
    a = FwdWorkday(
        Source(
            source_id="COM0417",
            company_id="COM0417",
            company="富卫集团",
            url=f"https://{FwdWorkday.host}/zh-CN/FWDcareersite/",
        ),
        cast(Session, Replay()),
        now,
    )
    fields = a.parse_detail(sample["detail"], sample["listing"])
    assert fields["work_type"] == kind
    assert "Privacy Notice" not in fields["requirements"]
    if name == "contract":
        assert fields["deadline"] == ""
        assert "6 Months Contract" in fields["title"]
        assert "Fresh graduate can be considered" in fields["requirements"]
        assert fields["duties"].startswith("PURPOSE")
    if name == "consultant":
        assert fields["duties"].startswith("Job Summary:")
        assert "Fresh graduate are strongly encouraged" in fields["requirements"]
        assert fields["location"] == "菲律宾、Philippines - BGC Taguig"
    if name == "registration":
        assert fields["duties"] == ""
        assert "への内定、誠におめでとうございます" in fields["requirements"]
    sample["detail"]["jobPostingInfo"]["jobPostingSiteId"] = "career"
    with pytest.raises(Exception, match="身份"):
        a.parse_detail(sample["detail"], sample["listing"])


def test_fwd_only_known_background_links_are_allowed(now):
    from job_crawler.adapters.workday import FwdWorkday

    a = FwdWorkday(
        Source(
            source_id="COM0417",
            company_id="COM0417",
            company="富卫",
            url=f"https://{FwdWorkday.host}/zh-CN/FWDcareersite/",
        ),
        cast(Session, Replay()),
        now,
    )
    sample = json.loads((FIX / "fwd-contract.json").read_text())
    html = sample["detail"]["jobPostingInfo"]["jobDescription"]
    with pytest.raises(Exception, match="新增正文链接"):
        a.body(html + '<a href="https://example.test/requirements.pdf">Qualification</a>')
    with pytest.raises(Exception, match="媒体"):
        a.body(html + '<img src="qualifications.png">')
    with pytest.raises(Exception, match="日文应届"):
        a.kind("2028新卒採用", "採用情報", "全职")
    assert a.kind("Internal Auditor", "新卒入社時研修", "全职") == "未明确校招"
