"""Public business-only replay of both Dingsheng catalogs and three details."""

import json
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest

from job_crawler.adapters.dingsheng import (
    COMPANY,
    EMPLOYER,
    FAIR,
    ROOT,
    UNIVERSITY,
    DingshengCampus,
)
from job_crawler.models import Source
from job_crawler.transport import Session

FIXTURE = json.loads((Path(__file__).parent / "fixtures/dingsheng/catalogs.json").read_text())


class Replay:
    last_evidence = "official-1"

    def __init__(self, fault: str = ""):
        self.fault = fault
        self.page = self
        self.current = "official-1"
        self.reads: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert not ready_endpoints
        if url == ROOT + "/channels/31.html":
            self.current = "official-1"
        else:
            assert url == UNIVERSITY + EMPLOYER + "/tab/1"
            self.current = "school"
        self.last_evidence = self.current

    def document(self, key: str) -> str:
        html = FIXTURE[key]
        if key == "official-2":
            if self.fault == "repeat":
                return FIXTURE["official-1"]
            if self.fault == "last":
                return html.replace('class="disabled"', 'class="enabled"')
        if key == "4026" and self.fault == "new_campus":
            return html.replace("环保专员（月薪", "2027应届毕业生 环保专员（月薪")
        if key == "school":
            if self.fault == "total":
                return html.replace("3个", "4个")
            if self.fault == "duplicate":
                return html.replace("2339825", "2339822")
        if key == "fair" and self.fault == "fair_scope":
            return html.replace("2340479", "2340480")
        if key == "2339825":
            if self.fault == "title":
                return html.replace("机械/电气技术员", "错误职位")
            if self.fault == "company":
                return html.replace(COMPANY, "其他公司")
            if self.fault == "id":
                return html.replace("2339825", "2339829")
            if self.fault == "date":
                return html.replace("2025-09-02发布", "日期未知")
            if self.fault == "attachment":
                return html.replace("机械维修、保养", '<img src="requirements.png">机械维修、保养')
            if self.fault == "intern":
                return html.replace("全职", "实习")
        return html

    async def content(self) -> str:
        return self.document(self.current)

    async def request_html(self, url: str, *, detail: bool = False) -> str:
        if url == ROOT + "/channels/31_2.html":
            key = "official-2"
        elif url == UNIVERSITY + FAIR:
            key = "fair"
        else:
            assert detail
            key = url.rsplit("/", 1)[1].removesuffix(".html")
        self.reads.append(key)
        self.last_evidence = key
        return self.document(key)


def adapter(replay: Replay, now: datetime) -> DingshengCampus:
    return DingshengCampus(
        Source(
            source_id="COM0488",
            company_id="COM0488",
            company=COMPANY,
            url=ROOT + "/channels/31.html",
        ),
        cast(Session, replay),
        now,
    )


async def test_both_full_catalogs_and_original_dates(now: datetime) -> None:
    replay = Replay()
    result = await adapter(replay, now).collect()
    assert not result.coverage_issues(), result.issues
    official, school = result.scopes
    assert official.unique == official.expected == official.skipped_out_of_scope == 17
    assert school.unique == school.expected == school.details == 3
    jobs = {j.source_key: j for j in result.jobs}
    assert jobs["2339822"].published == "2025-09-02"
    assert "2026届应届毕业生" in jobs["2339822"].requirements
    assert jobs["2340479"].published == "2025-09-04"
    assert "安环管培生" in jobs["2340479"].duties
    assert jobs["2339825"].address == "江苏省镇江市京口工业园区金润大道392号"
    assert jobs["2339825"].location == "江苏省镇江市"
    assert "26届应届生" in jobs["2339825"].duties
    assert all(j.deadline == "" and j.education == "本科" for j in jobs.values())
    assert len(replay.reads) == 22


@pytest.mark.parametrize(
    "fault",
    [
        "repeat",
        "last",
        "new_campus",
        "total",
        "duplicate",
        "fair_scope",
        "title",
        "company",
        "id",
        "date",
        "attachment",
        "intern",
    ],
)
async def test_incomplete_evidence_never_becomes_success(fault: str, now: datetime) -> None:
    result = await adapter(Replay(fault), now).collect()
    assert result.coverage_issues()
    if fault in {"title", "company", "id", "date", "attachment", "intern"}:
        assert len(result.jobs) == 2


async def test_incremental_reuse_still_verifies_both_catalogs(now: datetime) -> None:
    from job_crawler.incremental import IncrementalSource
    from job_crawler.models import Job, Scope

    original = await adapter(Replay(), now).collect()
    jobs = {j.source_key: j for j in original.jobs}

    class Reuse:
        def before_detail(
            self,
            entity: str,
            listing: object,
            scope: Scope,
            evidence: str,
            listing_job: Job | None = None,
        ) -> list[Job]:
            scope.reused_details += 1
            return [jobs[entity.removeprefix("job:")]]

    replay = Replay()
    instance = adapter(replay, now)
    instance.incremental = cast(IncrementalSource, Reuse())
    result = await instance.collect()
    assert not result.coverage_issues()
    assert len(result.jobs) == 3 and result.scopes[1].reused_details == 3
    assert len(replay.reads) == 19 and "fair" in replay.reads
