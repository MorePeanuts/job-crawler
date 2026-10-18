import copy
import json
from datetime import datetime
from typing import cast

import pytest

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.guangwu import (
    ANNOUNCEMENT,
    CATALOG,
    MIRROR,
    MIRROR_DATA,
    PATH,
    ROOT,
    UNITS,
    GuangwuCampus,
    array,
    deadline,
    details,
    positions,
    unit_tree,
)
from job_crawler.filtering import select
from job_crawler.models import Job, Scope, Source
from job_crawler.transport import CrawlError, Session


def row(**updates: object) -> dict[str, object]:
    return {
        "data-id": 20643,
        "所属企业": "广物汽贸",
        "company": "示例公司",
        "Department": "业务部",
        "jobName": "管理培训生",
        "link": "https://www.duomian.com/job/example.shtml",
        "edu": "本科及以上",
        "major": "管理类",
        "Category": "业务类",
        "address": "全国范围内，广佛为主",
        "job_description": "一、岗位职责\n协助经营分析。\n二、岗位要求\n熟悉办公软件。",
        "job_requirements": "本科及以上学历。",
        **updates,
    }


def html() -> str:
    return '<p>广物控股集团 校招岗位</p><ul class="ltab"><li><p data-id="10087">集团总部</p></li><li><p data-id="20643">广物汽贸</p><p data-id="20643">广物汽贸</p></li></ul>'


def units() -> list[dict[str, object]]:
    return [
        {"data-id": "10087", "company": "集团总部"},
        {"data-id": "20643", "company": "广物汽贸"},
    ]


def announcement() -> str:
    return '<p>发布时间：2026/01/31 到期时间：2026/01/31</p><div id="main_content">广物控股集团 国内2026届本科毕业生<p>3.截止时间</p><p>招满即止。</p><p>五、联系方式</p><img src="https://img.goworkla.cn/d2890820954c40e1b972a7d44c9a2b98.jpg"></div>'


def test_identity_preserves_shared_url_and_same_title_different_departments() -> None:
    tree = unit_tree(html(), units())
    rows = [row(), row(jobName="销售顾问"), row(Department="职能部")]
    parsed = positions(rows, tree)
    assert len({p.key for p in parsed}) == 3
    with pytest.raises(CrawlError, match="重复"):
        positions(rows + [row()], tree)


@pytest.mark.parametrize("change", ["empty", "unknown_unit", "owner", "shape", "title"])
def test_catalog_cannot_silently_drop_unrecognized_rows(change: str) -> None:
    rows = [row()]
    if change == "empty":
        rows = []
    elif change == "unknown_unit":
        rows[0]["data-id"] = 99
    elif change == "owner":
        rows[0]["所属企业"] = "其他单位"
    elif change == "shape":
        rows[0]["edu"] = {"name": "本科"}
    else:
        rows[0]["jobName"] = ""
    with pytest.raises(CrawlError):
        positions(rows, unit_tree(html(), units()))


@pytest.mark.parametrize("change", ["missing", "duplicate", "conflict", "pagination"])
def test_unit_tree_has_to_close(change: str) -> None:
    page, mapping = html(), units()
    if change == "missing":
        mapping.pop()
    elif change == "duplicate":
        mapping.append(mapping[0])
    elif change == "conflict":
        page = page.replace('data-id="10087">集团总部', 'data-id="20643">集团总部')
    else:
        page += '<div class="pagination">下一页</div>'
    with pytest.raises(CrawlError):
        unit_tree(page, mapping)


@pytest.mark.parametrize("change", ["url", "status", "wrapper"])
def test_array_requires_exact_public_endpoint_and_full_array(change: str) -> None:
    observed: dict[str, object] = {
        "url": CATALOG + "?_=123",
        "status": 200,
        "body": json.dumps([row()]),
    }
    assert len(array(observed, CATALOG)) == 1
    if change == "url":
        observed["url"] = UNITS
    elif change == "status":
        observed["status"] = 503
    else:
        observed["body"] = '{"data":[]}'
    with pytest.raises(CrawlError):
        array(observed, CATALOG)


def test_section_split_conflict_and_rolling_deadline_are_preserved() -> None:
    post = positions([row(edu="大专及以上")], unit_tree(html(), units()))[0]
    values = details(post)
    assert values["duties"] == "协助经营分析。"
    assert "熟悉办公软件" in values["requirements"] and "管理类" in values["requirements"]
    assert values["education"] == "来源冲突（摘要：大专及以上；正文：本科）"
    assert deadline(announcement()) == "招满即止"
    for invalid in [
        announcement().replace("招满即止", "2026年10月31日"),
        announcement().replace("2026届", "2027届"),
        announcement().replace("</div>", '<a href="/jobs.pdf">更多岗位</a></div>'),
        announcement().replace("</div>", '<img src="/new.jpg"></div>'),
    ]:
        with pytest.raises(CrawlError):
            deadline(invalid)
    assert (
        deadline(
            announcement().replace(
                "</div>", '<a href="javascropt:void(0)">登录后查看详情</a></div>'
            )
        )
        == "招满即止"
    )


class Replay:
    last_evidence = "initial"

    def __init__(self) -> None:
        self.page = self
        self.url = ""
        self.rows = [row(), row(jobName="销售顾问")]
        self.mismatch = False

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url in {ROOT + PATH, MIRROR, ANNOUNCEMENT}
        self.url = url
        self.last_evidence = url

    async def content(self) -> str:
        return announcement() if self.url == ANNOUNCEMENT else html()

    async def observed(self, endpoint: str) -> dict[str, object]:
        self.last_evidence = endpoint
        rows = units() if endpoint == UNITS else copy.deepcopy(self.rows)
        if self.mismatch and endpoint == MIRROR_DATA:
            rows.pop()
        return {"url": endpoint, "status": 200, "body": json.dumps(rows)}


def source() -> Source:
    return Source(
        source_id="COM0243",
        company_id="COM0243",
        company="广东省广物控股集团有限公司",
        url=ROOT + PATH,
    )


async def test_all_units_and_review_records_have_evidence_and_no_fabricated_dates(
    now: datetime,
) -> None:
    replay = Replay()
    result = await GuangwuCampus(source(), cast(Session, replay), now).collect()
    assert not result.coverage_issues()
    assert [(s.expected, s.details) for s in result.scopes] == [(2, 2), (0, 0), (2, 2)]
    assert len(result.jobs) == 2
    for job in result.jobs:
        assert job.company == source().company
        assert job.published == job.address == ""
        assert job.location == "全国范围内，广佛为主" and len(job.evidence) == 4
        assert select(job, "all", now).reason == "unparsed_deadline"
        assert job.deadline == "招满即止"


async def test_changed_mirror_stops_acceptance(now: datetime) -> None:
    replay = Replay()
    replay.mismatch = True
    result = await GuangwuCampus(source(), cast(Session, replay), now).collect()
    assert result.coverage_issues() and not result.jobs


async def test_bad_detail_keeps_other_rows(now: datetime) -> None:
    replay = Replay()
    replay.rows[1]["job_description"] = '<img src="attachment.png">'
    result = await GuangwuCampus(source(), cast(Session, replay), now).collect()
    assert result.coverage_issues() and len(result.jobs) == 1
    assert result.scopes[-1].unique == 2 and result.scopes[-1].details == 1


async def test_incremental_fingerprint_tracks_full_text_and_unresolved_deadline(
    now: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = await GuangwuCampus(source(), cast(Session, Replay()), now).collect()
    cached = {j.source_key: j for j in first.jobs}
    states = []

    def before(
        self: Adapter,
        entity: str,
        listing: object,
        scope: Scope,
        listing_job: Job | None = None,
        *,
        evidence: str | None = None,
    ) -> list[Job]:
        assert evidence == CATALOG
        states.append(listing)
        scope.reused_details += 1
        return [cached[entity]]

    monkeypatch.setattr(Adapter, "before_detail", before)
    second = await GuangwuCampus(source(), cast(Session, Replay()), now).collect()
    assert not second.coverage_issues() and second.scopes[-1].reused_details == 2
    assert all(
        isinstance(s, dict) and s["deadline"] == "招满即止" and s["description"] for s in states
    )
