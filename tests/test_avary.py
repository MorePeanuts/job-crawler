"""Sanitized legacy park pages and scope/identity failure replays."""

import json
from datetime import datetime
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest

from job_crawler.adapters.avary import ROOT, AvaryCampus, catalog, detail, park_url, search_url
from job_crawler.incremental import IncrementalSource
from job_crawler.models import Job, Scope, Source
from job_crawler.transport import CrawlError, Session

PAGES = json.loads((Path(__file__).parent / "fixtures/avary/pages.json").read_text())


class Replay:
    last_evidence = "initial"

    def __init__(self, fault: str = ""):
        self.fault = fault
        self.page = self
        self.url = ""
        self.opened: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url.startswith(ROOT + "/") and not ready_endpoints
        assert "/Portal/" not in url
        self.url = url
        self.opened.append(url)
        self.last_evidence = url
        if self.fault == "detail_failure" and "jobId=621074950" in url:
            raise TimeoutError("detail temporarily unavailable")

    def snapshot(self, label: str, html: str) -> str:
        self.last_evidence = label
        return label

    async def content(self) -> str:
        parts = urlsplit(self.url)
        query = parse_qs(parts.query)
        if parts.path == "/campus":
            html = PAGES["root"]
            if self.fault == "new_park":
                html += '<a class="icon5d" title="新园区" href="/newxz?sub=new"></a>'
            return html
        if "jobId" in query:
            return PAGES[query["jobId"][0]]
        park = query["sub"][0]
        page = int(query.get("PageIndex", ["1"])[0])
        if park == "sz" and page > 1:
            if self.fault == "repeat_page":
                return PAGES["sz"]
            return PAGES["sz-empty"]
        if self.fault == "search_mismatch" and park == "sz" and "PageIndex" in query:
            return PAGES["sz-empty"]
        if self.fault == "missing_zero" and park == "ha":
            return PAGES["ha"].replace("暂无职位", "加载中")
        if self.fault == "missing_yk_declaration" and park == "sz":
            return PAGES["sz"].replace("/ykxz?sub=yk", "/changed")
        return PAGES[park]


def adapter(replay: Replay, now: datetime) -> AvaryCampus:
    return AvaryCampus(
        Source(
            source_id="COM0379",
            company_id="COM0379",
            company="鹏鼎控股(深圳)股份有限公司",
            url=ROOT + "/campus",
        ),
        cast(Session, replay),
        now,
    )


async def test_complete_all_parks_ends_at_explicit_empty_page_and_retains_source_years(
    now: datetime,
) -> None:
    replay = Replay()
    result = await adapter(replay, now).collect()
    assert not result.coverage_issues()
    assert [(s.unique, s.details, s.terminal) for s in result.scopes] == [
        (4, 4, True),
        (0, 0, True),
        (0, 0, True),
        (0, 0, True),
    ]
    assert search_url("sz", 1) in replay.opened and search_url("sz", 2) in replay.opened
    assert all(park_url(park) in replay.opened for park in ["sz", "ha", "qhd", "yk"])
    jobs = {j.source_key: j for j in result.jobs}
    technical = jobs["620545075"]
    assert technical.title == "26届本硕应届生" and technical.published == "2023-05-20"
    assert technical.location == "宝安区" and technical.address == technical.deadline == ""
    assert "1. 26届本/硕应届生" in technical.requirements
    assert "研发类、工程技术类、生产管理类、职能类" in technical.duties
    assert all(j.company == "鹏鼎控股(深圳)股份有限公司" for j in result.jobs)
    for key in ["621074950", "620956925", "620837211"]:
        job = jobs[key]
        assert job.duties == job.requirements == job.education == ""
        assert job.location == "台湾省" and job.field_sources["duties"].startswith(
            "source_missing:"
        )
    assert jobs["620837211"].published == "2024-03-01"


@pytest.mark.parametrize(
    "fault",
    ["new_park", "repeat_page", "search_mismatch", "missing_zero", "missing_yk_declaration"],
)
async def test_incomplete_park_or_pagination_never_becomes_complete(
    fault: str, now: datetime
) -> None:
    result = await adapter(Replay(fault), now).collect()
    assert result.coverage_issues()


async def test_one_detail_failure_preserves_others_and_still_traverses_empty_parks(
    now: datetime,
) -> None:
    result = await adapter(Replay("detail_failure"), now).collect()
    assert len(result.jobs) == 3 and len(result.scopes) == 4
    assert result.coverage_issues() and result.scopes[0].details == 3
    assert any(i.job_key == "621074950" for i in result.issues)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('value="1^-1"', 'value="1^8"'),
        ('id="hidcity" type="hidden" value=""', 'id="hidcity" type="hidden" value="4403"'),
        ('value="3^12"', 'value="3^11"'),
        ("jobId=621074950&amp;sub=sz", "jobId=621074950&amp;sub=ha"),
        ("2026-03-03", "invalid-date"),
        ('id="xyzp"', 'id="social"'),
    ],
)
def test_filter_identity_or_date_changes_are_rejected(old: str, new: str) -> None:
    assert old in PAGES["sz"]
    with pytest.raises((ValueError, CrawlError)):
        catalog(PAGES["sz"].replace(old, new), "sz")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("jid=620545075", "jid=999"),
        ("<h2>26届本硕应届生</h2>", "<h2>其他岗位</h2>"),
        ("招聘单位：深圳园区", "招聘单位：其他园区"),
        ("发布时间：2023-05-20", "发布时间：2026-05-20"),
        ("工作职责：", "未知章节："),
        ("岗位类别：", '<img src="attachment.png">岗位类别：'),
    ],
)
def test_detail_association_body_boundaries_and_attachments(old: str, new: str) -> None:
    row = catalog(PAGES["sz"], "sz")[-1]
    assert old in PAGES[row["id"]]
    with pytest.raises((ValueError, CrawlError)):
        detail(PAGES[row["id"]].replace(old, new), row, "sz")


async def test_multiple_nonempty_pages_preserve_same_title_distinct_source_ids(
    now: datetime,
) -> None:
    class TwoPages(Replay):
        async def content(self) -> str:
            query = parse_qs(urlsplit(self.url).query)
            if query.get("PageIndex") == ["2"]:
                return PAGES["sz"].replace("jobId=6", "jobId=7")
            if query.get("jobId", [""])[0].startswith("7"):
                key = query["jobId"][0]
                return PAGES["6" + key[1:]].replace("jid=6", "jid=7")
            return await super().content()

    replay = TwoPages()
    result = await adapter(replay, now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 8
    assert result.scopes[0].expected == result.scopes[0].details == 8
    assert search_url("sz", 3) in replay.opened
    assert len({j.title for j in result.jobs}) == 4


def test_empty_park_requires_real_table_and_department_selector() -> None:
    with pytest.raises(CrawlError):
        catalog(PAGES["ha"].replace("暂无职位", ""), "ha")
    with pytest.raises(CrawlError):
        catalog(PAGES["yk"].replace('id="n"', 'id="missing"'), "yk")


async def test_incremental_reuse_does_not_skip_search_end_or_other_parks(now: datetime) -> None:
    class Reuse:
        def before_detail(
            self,
            entity: str,
            listing: object,
            scope: Scope,
            evidence: str,
            listing_job: Job | None = None,
        ) -> list[Job]:
            assert listing_job is not None
            scope.reused_details += 1
            return [listing_job]

    replay = Replay()
    instance = adapter(replay, now)
    instance.incremental = cast(IncrementalSource, Reuse())
    result = await instance.collect()
    assert not result.coverage_issues() and result.scopes[0].reused_details == 4
    assert not any("jobId=" in url for url in replay.opened)
    assert search_url("sz", 2) in replay.opened and park_url("yk") in replay.opened
