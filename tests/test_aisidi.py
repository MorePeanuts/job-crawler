from datetime import datetime
from typing import cast
from urllib.parse import urlencode

import pytest

from job_crawler.adapters.aisidi import (
    ANNOUNCEMENT,
    COMPANY,
    EMPLOYER,
    AisidiCampus,
    campus_rows,
    detail,
    match_rows,
)
from job_crawler.adapters.base import Adapter
from job_crawler.adapters.tfme import ROOT, catalog
from job_crawler.models import Job, Scope, Source
from job_crawler.transport import CrawlError, Session

TITLES = [
    "储备店长",
    "MyCoach讲师",
    "营运管理岗",
    "电商运营岗",
    "产品运营岗",
    "人力资源岗",
    "财务管理岗",
    "IT技术岗",
]


def listing() -> str:
    rows = "".join(
        f'<tr><td><a href="{ROOT}/job/view/id/{i}">{title}{"管培生" if i == 4 else ""}</a>'
        f'</td><td><a class="apply_job" data-id="{i}">投递</a></td></tr>'
        for i, title in enumerate(TITLES, 1)
    )
    return f'<div class="unit-info"><div class="title"><h5>{COMPANY}</h5></div></div><p v-text-job-total>8个</p><table>{rows}</table>'


def announcement() -> str:
    cards = "".join(
        f'<div class="career-job job-item"><a class="career-job-name" href="/detail/job?id={i + 100}&amp;career_id=722314">2027届管理培训生--{title}</a>'
        f'<div class="job-item-line2"><span title="要求学历">本科及以上</span>'
        f'<span title="工作地点">{"全国" if i <= 3 else "深圳市"}</span></div></div>'
        for i, title in enumerate(TITLES, 1)
    )
    return f'<div id="pane-detail">{COMPANY}002416零售事业群2027届</div><div id="tab-jobs">招聘职位 (8)</div><div id="pane-jobs">{cards}</div>'


def job_page(identity: str) -> str:
    number = int(identity)
    title = TITLES[number - 1] + ("管培生" if number == 4 else "")
    share = "https://connect.qq.com/widget/shareqq/index.html?" + urlencode(
        {"url": ROOT + "/job/view/id/" + identity}
    )
    return f'''<div class="title-message"><span class="title">{title}</span>
    <a href="{EMPLOYER}">{COMPANY}</a></div>
    <div class="message-info">不限 | 深圳市 | 不限</div>
    <div class="share-link"><a class="icon-qq" href="{share}">分享</a></div>
    <li class="full-width">需求专业：工商管理</li>
    <div class="details-mge"><h5 class="mge-title">职位详情</h5><div class="aContent">
    <p>岗位职责：负责业务管理。</p><p>要求：专业不限，市场营销优先。</p><p>良好沟通能力。</p><p><br></p>
    </div></div><div class="details-address"><div class="address-container"><p>深圳市南山区南山金融大厦</p></div></div>
    <div class="details-mge"><h5 class="mge-title">公司信息</h5><div class="aContent">历史公司介绍不可充当职责</div></div>'''


def rows() -> list[dict[str, str]]:
    return match_rows(
        catalog(listing(), company=COMPANY, title_suffix="")[1], campus_rows(announcement())
    )


def test_eight_matched_jobs_keep_national_location_and_explicit_degree() -> None:
    matched = rows()
    assert len(matched) == 8
    assert matched[3]["title"] == "电商运营岗管培生"
    assert matched[3]["campus_title"] == "2027届管理培训生--电商运营岗"
    for row in matched:
        values = detail(job_page(row["id"]), row)
        assert row["education"] == "本科及以上"
        assert values["duties"] == "负责业务管理。"
        assert "良好沟通能力" in values["requirements"]
        assert "历史公司介绍" not in str(values)
        if int(row["id"]) <= 3:
            assert row["location"] == "全国" and values["address"] == ""
        else:
            assert row["location"] == "深圳市"
            assert values["address"] == "深圳市南山区南山金融大厦"


@pytest.mark.parametrize(
    "change", ["count", "duplicate", "title", "employer", "type", "page", "identity"]
)
def test_changed_announcement_fails_instead_of_cross_source_guessing(change: str) -> None:
    html = announcement()
    if change == "count":
        html = html.replace("职位 (8)", "职位 (9)")
    elif change == "duplicate":
        html = html.replace("id=102", "id=101")
    elif change == "title":
        html = html.replace("IT技术岗", "额外未知岗位")
    elif change == "employer":
        html = html.replace(COMPANY, "其他公司")
    elif change == "type":
        html = html.replace("IT技术岗", "实习生")
    elif change == "identity":
        html = html.replace("career_id=722314", "career_id=999999")
    else:
        html = html.replace(
            '<div id="pane-jobs">', '<div id="pane-jobs"><div class="el-pagination">下一页</div>'
        )
    with pytest.raises(CrawlError):
        match_rows(catalog(listing(), company=COMPANY, title_suffix="")[1], campus_rows(html))


@pytest.mark.parametrize("change", ["employer", "id", "body", "order", "attachment"])
def test_detail_changes_preserve_identity_and_body_contract(change: str) -> None:
    html = job_page("1")
    if change == "employer":
        html = html.replace("345026", "999999")
    elif change == "id":
        html = html.replace("%2Fid%2F1", "%2Fid%2F2")
    elif change == "body":
        html = html.replace("<p>岗位职责：负责业务管理。</p>", "未处理正文")
    elif change == "order":
        html = html.replace("岗位职责：负责业务管理。", "本科及以上学历")
    else:
        html = html.replace("负责业务管理。", '<img src="/requirements.png">')
    with pytest.raises(CrawlError):
        detail(html, rows()[0])


class Replay:
    last_evidence = "list-evidence"

    def __init__(self, fail: bool = False):
        self.page = self
        self.current = ""
        self.reads: list[str] = []
        self.fail = fail

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.current = url
        if url in {EMPLOYER + "/tab/1", ANNOUNCEMENT}:
            return
        self.reads.append(url)
        if self.fail and url.endswith("/1"):
            raise CrawlError("request_failed", "临时详情失败")

    async def content(self) -> str:
        if self.current == EMPLOYER + "/tab/1":
            return listing()
        if self.current == ANNOUNCEMENT:
            return announcement()
        return job_page(self.current.rsplit("/", 1)[-1])

    def snapshot(self, label: str, html: str) -> str:
        self.last_evidence = self.current
        return self.last_evidence


def source() -> Source:
    return Source(source_id="COM0290", company_id="COM0290", company=COMPANY, url=EMPLOYER)


@pytest.mark.parametrize("fail", [False, True])
async def test_full_or_partial_details_keep_dates_unknown(fail: bool, now: datetime) -> None:
    replay = Replay(fail)
    result = await AisidiCampus(source(), cast(Session, replay), now).collect()
    assert bool(result.coverage_issues()) == fail
    assert result.scopes[0].unique == 8
    assert result.scopes[0].details == (7 if fail else 8)
    assert len(result.jobs) == (7 if fail else 8)
    for job in result.jobs:
        assert job.published == job.deadline == ""
        assert job.evidence == ["list-evidence", ANNOUNCEMENT, job.source_url]
        assert job.education == "本科及以上"


async def test_reuse_receives_both_sources_and_skips_detail(
    monkeypatch: pytest.MonkeyPatch, now: datetime
) -> None:
    def before(
        self: Adapter,
        entity: str,
        listing: object,
        scope: Scope,
        listing_job: Job | None = None,
        *,
        evidence: str | None = None,
    ) -> list[Job]:
        assert isinstance(listing, dict) and listing["campus_id"] and listing["location"]
        assert evidence == "list-evidence"
        scope.reused_details += 1
        return [self.job(entity, title="历史详情", source_url=listing["url"])]

    monkeypatch.setattr(Adapter, "before_detail", before)
    replay = Replay()
    result = await AisidiCampus(source(), cast(Session, replay), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].reused_details == 8 and not replay.reads
