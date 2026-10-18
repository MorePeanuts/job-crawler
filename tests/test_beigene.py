"""Dual-platform identity isolation and source-qualified graduate recruitment."""

import copy
import json
from pathlib import Path
from typing import cast

import pytest

from job_crawler.adapters.beigene import (
    BeigeneMoka,
    BeigeneMoseeker,
    BeigeneRecruitment,
    BeigeneWorkday,
)
from job_crawler.adapters.workday import BASE_QUERY
from job_crawler.incremental import IncrementalSource
from job_crawler.models import Source
from job_crawler.transport import Session

FIX = Path(__file__).parent / "fixtures/beigene"


def sample(name):
    return json.loads((FIX / f"{name}.json").read_text())


class Page:
    async def evaluate(self, script):
        assert "TurboApply" in script
        return "0123456789abcdef"


class Replay:
    page = Page()
    last_evidence = "entry"

    def __init__(self, fault=""):
        self.fault = fault
        self.calls = []
        self.moka = [sample(f"moka-{n}") for n in range(3)]
        self.rows = []
        self.details = {}
        for n in range(22):
            d = sample("gra")
            key = f"Fellow_R{n}"
            row = d["listing"]
            row.update(
                title=f"GRA Fellow {n}",
                externalPath="/job/Remote-US/" + key,
                bulletFields=[f"R{n}"],
            )
            i = d["detail"]["jobPostingInfo"]
            i.update(
                title=row["title"],
                jobReqId=f"R{n}",
                jobPostingId=key,
                externalUrl=f"https://{BeigeneWorkday.host}/BeiGene" + row["externalPath"],
            )
            self.rows.append(row)
            self.details[key] = d["detail"]

    async def open(self, url, *, ready_endpoints=()):
        self.calls.append(("open", url))
        if self.fault == "moka_entry" and "mokahr" in url:
            raise ValueError("campus unavailable")
        if self.fault == "global_entry" and "workday" in url:
            raise ValueError("global unavailable")
        if "#/job/" in url:
            self.detail_id = url.rsplit("/", 1)[-1]
        self.last_evidence = url

    async def observed_path(self, path):
        if path.endswith("/jobs/v2"):
            return {
                "url": "https://app.mokahr.com" + path,
                "post_data": json.dumps(
                    {
                        "orgId": "beigene",
                        "siteId": "98935",
                        "site": "campus",
                        "limit": 2,
                        "offset": 0,
                        "needStat": True,
                        "jobIdTopList": [],
                        "customFields": {},
                    }
                ),
            }
        detail = next(x["detail"] for x in self.moka if x["detail"]["id"] == self.detail_id)
        return {
            "url": "https://app.mokahr.com" + path,
            "body": json.dumps({"code": 0, "data": detail}),
        }

    async def observed(self, path):
        return {"url": path, "post_data": json.dumps(BASE_QUERY)}

    async def request(self, url, *, payload=None, detail=False):
        self.calls.append((url, copy.deepcopy(payload)))
        self.last_evidence = url + ":" + str(payload)
        if "mokahr" in url:
            assert payload is not None
            if detail:
                d = copy.deepcopy(
                    next(x["detail"] for x in self.moka if x["detail"]["id"] == payload["jobId"])
                )
                if self.fault == "moka_identity":
                    d["id"] = "other"
                return {"code": 0, "data": d}
            offset = payload["offset"]
            rows = [x["listing"] for x in self.moka[offset : offset + 2]]
            return {"code": 0, "data": {"jobStats": {"total": 3}, "jobs": rows}}
        if url.endswith("/jobs"):
            assert payload is not None
            offset = payload["offset"]
            rows = copy.deepcopy(self.rows[offset : offset + 20])
            if self.fault == "global_duplicate" and offset == 20:
                rows[0] = self.rows[0]
            return {"total": 22, "jobPostings": rows}
        key = url.rsplit("/", 1)[-1]
        row = next(x for x in self.rows if x["externalPath"].endswith(key))
        assert (
            url == f"https://{BeigeneWorkday.host}/wday/cxs/beigene/BeiGene" + row["externalPath"]
        )
        d = copy.deepcopy(self.details[key])
        if self.fault == "global_identity" and key == "Fellow_R1":
            d["jobPostingInfo"]["jobReqId"] = "wrong"
        return d


def adapter(now, replay=None):
    a = BeigeneRecruitment(
        Source(
            source_id="COM0384",
            company_id="COM0384",
            company="百济神州有限公司",
            url="https://app.mokahr.com" + BeigeneMoka.path,
        ),
        cast(Session, replay or Replay()),
        now,
    )

    a.children = (BeigeneMoka, BeigeneWorkday)
    return a


@pytest.mark.asyncio
async def test_two_independent_catalogs_keep_identity_and_date(now):
    r = Replay()
    a = adapter(now, r)
    result = await a.collect()
    assert not result.coverage_issues()
    assert [s.details for s in result.scopes] == [3, 22]
    assert len(result.jobs) == len({j.key for j in result.jobs}) == 25
    assert all(j.company == "百济神州有限公司" and j.source_id == "COM0384" for j in result.jobs)
    assert all(j.source_key.startswith("moka:") for j in result.jobs[:3])
    assert all(j.source_key.startswith("workday:") for j in result.jobs[3:])
    assert result.jobs[3].published == "2026-09-16" and not result.jobs[3].deadline
    assert "July 2027" in result.jobs[3].requirements
    assert "Essential Functions" in result.jobs[3].duties
    assert "75k/Year" in result.jobs[3].requirements
    assert [p["offset"] for u, p in r.calls if u.endswith("/jobs")] == [0, 20, 0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault,minimum",
    [
        ("moka_entry", 22),
        ("global_entry", 3),
        ("moka_identity", 23),
        ("global_identity", 24),
        ("global_duplicate", 23),
    ],
)
async def test_one_failed_branch_keeps_other_branch_and_reports_gap(now, fault, minimum):
    result = await adapter(now, Replay(fault)).collect()
    assert result.coverage_issues() and result.issues
    assert len(result.jobs) >= minimum


@pytest.mark.parametrize(
    "name,kind",
    [
        ("gra", "校招"),
        ("medical", "校招"),
        ("ai-fellow", "未明确校招"),
        ("portuguese-intern", "实习"),
    ],
)
async def test_source_qualified_scope_and_intact_inline_words(now, name, kind):
    a = BeigeneWorkday(adapter(now).source, cast(Session, Replay()), now)
    d = sample(name)
    fields = a.parse_detail(d["detail"], d["listing"])
    assert fields["work_type"] == kind
    assert "Global Competencies" not in fields["requirements"]
    if name == "gra":
        assert "Master’s in Regulatory Affairs" in fields["requirements"]
        assert "July 2027" in fields["requirements"]
        assert "completed" in fields["requirements"]
    if name == "medical":
        assert "recent pharmacy graduate" in fields["requirements"]
        assert "prior" in (fields["duties"] + fields["requirements"]).lower()


@pytest.mark.parametrize(
    "append",
    ['<a href="https://example.org/more-jobs">more jobs</a>', '<img src="qualification.png">'],
)
def test_unknown_links_media_require_review(now, append):
    a = BeigeneWorkday(adapter(now).source, cast(Session, Replay()), now)
    with pytest.raises(Exception, match="待"):
        a.body(sample("gra")["detail"]["jobPostingInfo"]["jobDescription"] + append)


class Cache:
    def __init__(self):
        self.entries = {}
        self.seen = []
        self.reuse = False

    def before_detail(self, entity, listing, scope, evidence, listing_job=None):
        self.seen.append(entity)
        if not self.reuse:
            return None
        jobs = copy.deepcopy(self.entries[entity])
        scope.reused_details += 1
        return jobs

    def remember(self, entity, listing, jobs):
        self.entries[entity] = copy.deepcopy(jobs)


@pytest.mark.asyncio
async def test_incremental_uses_platform_namespaces_and_still_reads_both_catalogs(now):
    cache = Cache()
    a = adapter(now)
    a.incremental = cast(IncrementalSource, cache)
    first = await a.collect()
    assert not first.coverage_issues()
    assert len(cache.entries) == 25
    assert all(x.startswith(("moka:job:", "workday:job:")) for x in cache.entries)
    cache.reuse = True
    r = Replay()
    a = adapter(now, r)
    a.incremental = cast(IncrementalSource, cache)
    second = await a.collect()
    assert not second.coverage_issues()
    assert [s.reused_details for s in second.scopes] == [3, 22]
    assert [j.key for j in first.jobs] == [j.key for j in second.jobs]
    assert not any("#/job/" in str(p) or "/job/Remote-US/" in u for u, p in r.calls)


@pytest.mark.asyncio
async def test_wrong_site_entry_never_opens_either_platform(now):
    r = Replay()
    a = adapter(now, r)
    a.source.url = "https://app.mokahr.com/campus-recruitment/beigene/118622#/jobs"
    result = await a.collect()
    assert result.issues[0].code == "entry_mismatch" and not r.calls


class MoseekerReplay:
    last_evidence = "entry"

    def __init__(self, fault=""):
        self.calls = []
        self.fault = fault

    async def open(self, url, *, ready_endpoints=()):
        assert url == "https://www.moseeker.com" + BeigeneMoseeker.path

    async def request_html(self, url):
        self.calls.append(url)
        self.last_evidence = url
        if "/positions/" in url:
            page = 2 if "pageNum=2" in url else 1
            nums = range(18) if page == 1 else range(18, 19)
            total = 20 if self.fault == "total" and page == 2 else 19
            cards = []
            for n in nums:
                if self.fault == "duplicate" and page == 2:
                    n = 0
                cards.append(
                    f'<a class="PositionList__job-item" title="百济神州" href="/position/index/pid/{n}"><h4 class="job-title">Research Investigator, BeiGene Institute {n}</h4></a>'
                )
            return f"<script>var totalNum:{total};</script>" + "".join(cards)
        n = url.rsplit("/", 1)[-1]
        html = (
            (FIX / "moseeker-campus.html")
            .read_text()
            .replace("2446362", n)
            .replace(
                "Research Investigator, BeiGene Institute",
                f"Research Investigator, BeiGene Institute {n}",
            )
        )
        if self.fault == "identity" and n == "1":
            html = html.replace("positionId:1", "positionId:999")
        return html


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["", "identity", "duplicate", "total"])
async def test_moseeker_actual_paging_contract_and_partial_failures(now, fault):
    r = MoseekerReplay(fault)
    a = BeigeneMoseeker(
        adapter(now).source.model_copy(
            update={"url": "https://www.moseeker.com" + BeigeneMoseeker.path}
        ),
        cast(Session, r),
        now,
    )
    result = await a.collect()
    if fault:
        assert result.coverage_issues() and len(result.jobs) == 18
    else:
        assert not result.coverage_issues() and len(result.jobs) == 19
        assert result.scopes[0].expected == result.scopes[0].details == 19
        assert all(j.source_key.startswith("moseeker:") for j in result.jobs)
        assert len([u for u in r.calls if "/positions/" in u]) == 3
        assert all(not j.published and not j.deadline for j in result.jobs)
        assert result.jobs[0].education == "博士"
        assert result.jobs[0].location == "上海"


@pytest.mark.parametrize(
    "name,kind", [("campus", "校招"), ("intern", "实习"), ("contract", "合同工")]
)
def test_moseeker_real_types_and_unknown_date(now, name, kind):
    from bs4 import BeautifulSoup

    a = BeigeneMoseeker(adapter(now).source, cast(Session, MoseekerReplay()), now)
    html = (FIX / f"moseeker-{name}.html").read_text()
    ids = {"campus": "2446362", "intern": "2196065", "contract": "2909779"}
    heading = BeautifulSoup(html, "html.parser").select_one("h2.postion-title")
    assert heading is not None
    title = heading.get_text(" ", strip=True)
    fields = a.parse_detail(
        html,
        {
            "id": ids[name],
            "title": title,
            "url": "https://www.moseeker.com/position/index/pid/" + ids[name],
        },
    )
    assert fields["work_type"] == kind
    assert "published" not in fields and "deadline" not in fields


def test_moseeker_real_catalog_total_and_terminal_page(now):
    a = BeigeneMoseeker(adapter(now).source, cast(Session, MoseekerReplay()), now)
    first, rows = a.catalog((FIX / "moseeker-page-1.html").read_text())
    final, end = a.catalog((FIX / "moseeker-page-20.html").read_text())
    assert first == final == 351 and len(rows) == 18 and len(end) == 9
    assert len({r["id"] for r in rows + end}) == 27


@pytest.mark.asyncio
async def test_three_platform_collection_including_legacy_failure_and_cache(now):
    class TripleReplay(Replay):
        def __init__(self, fault=""):
            super().__init__()
            self.legacy = MoseekerReplay(fault)

        async def request_html(self, url):
            result = await self.legacy.request_html(url)
            self.last_evidence = self.legacy.last_evidence
            return result

    cache = Cache()
    r = TripleReplay()
    a = adapter(now, r)
    a.children = (BeigeneMoka, BeigeneWorkday, BeigeneMoseeker)
    a.incremental = cast(IncrementalSource, cache)
    first = await a.collect()
    assert not first.coverage_issues() and len(first.jobs) == 44
    assert [s.details for s in first.scopes] == [3, 22, 19]
    assert sum(k.startswith("moseeker:job:") for k in cache.entries) == 19
    cache.reuse = True
    r = TripleReplay()
    a = adapter(now, r)
    a.children = BeigeneRecruitment.children
    a.incremental = cast(IncrementalSource, cache)
    second = await a.collect()
    assert not second.coverage_issues() and [j.key for j in first.jobs] == [
        j.key for j in second.jobs
    ]
    assert [s.reused_details for s in second.scopes] == [3, 22, 19]
    assert all("/positions/" in url for url in r.legacy.calls)
    a = adapter(now, TripleReplay("identity"))
    a.children = BeigeneRecruitment.children
    partial = await a.collect()
    assert partial.coverage_issues() and len(partial.jobs) == 43


def test_moseeker_explicit_lower_degree_exception_is_not_hidden_by_phd_field(now):
    a = BeigeneMoseeker(adapter(now).source, cast(Session, MoseekerReplay()), now)
    html = (
        (FIX / "moseeker-campus.html")
        .read_text()
        .replace("Requirements:", "Requirements: 或本科教育学历，专业能力表现卓越。")
    )
    fields = a.parse_detail(
        html,
        {
            "id": "2446362",
            "title": "Research Investigator, BeiGene Institute",
            "url": "https://www.moseeker.com/position/index/pid/2446362",
        },
    )
    assert fields["education"] == "博士；或本科教育学历，专业能力表现卓越"
    assert "或本科教育学历，专业能力表现卓越" in fields["requirements"]


@pytest.mark.parametrize("name", ["moka-1", "moka-early-education", "moka-plain"])
def test_moka_english_qualifications_preserve_real_blocks_and_education(now, name):
    a = BeigeneMoka(adapter(now).source, cast(Session, Replay()), now)
    d = sample(name)
    job = a._job(d["detail"], d["listing"], "real-detail", is_detail=True)
    assert job.duties and job.requirements and not a.result.warnings
    assert job.field_sources["requirements"].endswith("明确英文/双语小标题")
    if name == "moka-early-education":
        assert "A Ph.D. degree" in job.requirements
        assert "Conduct QSP" in job.duties and "Conduct QSP" not in job.requirements
    if name == "moka-plain":
        assert "Bachelor's degree" in job.requirements
        assert "Responsible for testing stability samples" in job.duties


def test_moka_no_explicit_qualification_heading_keeps_source_and_warning(now):
    a = BeigeneMoka(adapter(now).source, cast(Session, Replay()), now)
    d = sample("moka-no-heading")
    job = a._job(d["detail"], d["listing"], "detail", is_detail=True)
    assert job.duties and not job.requirements
    assert a.result.warnings[0].code == "field_missing"


def test_moka_sentence_mentioning_requirements_does_not_become_heading(now):
    a = BeigeneMoka(adapter(now).source, cast(Session, Replay()), now)
    d = sample("moka-plain")
    d["detail"]["jobDescription"] = (
        "<p>Collect requirements from product teams and maintain scientific records.</p><p>Provide support to colleagues in research programmes.</p>"
    )
    job = a._job(d["detail"], d["listing"], "detail", is_detail=True)
    assert not job.requirements and "Collect requirements" in job.duties
