"""HEBUT fair profile and detail boundaries for group-owned employers."""

from datetime import datetime
from typing import cast

import pytest

from job_crawler.adapters.hebut_fair import TENANTS, HebutFair2027, detail_job, profile_jobs
from job_crawler.models import Source
from job_crawler.transport import CrawlError, Session

ROOT = "https://career.hebut.edu.cn"


def profile(*, name: str = "江苏敬业钢铁有限责任公司", fair: bool = True) -> str:
    fair_link = (
        '<table class="company_index_info_zph"><a '
        'href="/recruitment/content/type/1/id/120.html">'
        "河北工业大学2027届毕业生秋季双选会</a></table>"
        if fair
        else ""
    )
    return (
        f'<div class="company_index"><div class="p1">{name}</div></div>'
        f'<div class="company_index_info">隶属于敬业集团{fair_link}</div>'
        '<a class="lizw" href="/correcruit/content/id/81624.html">'
        '<div class="zw_title"><p class="p1">储备干部</p>'
        '<p class="p2">2026-10-07</p></div></a>'
        '<a class="lizw" href="/correcruit/content/id/70000.html">'
        '<div class="zw_title"><p class="p1">旧岗位</p>'
        '<p class="p2">2025-10-07</p></div></a>'
    )


def detail(*, employer: str = "江苏敬业钢铁有限责任公司", title: str = "储备干部") -> str:
    return (
        '<div class="zpxq"><div class="title">'
        f'{title}<span class="gongzi">6000元</span></div>'
        '<div class="info"><a href="/company/index/id/19621.html">'
        f'【{employer}】</a><span class="fb">发布时间：2026-10-07</span>'
        "<p>工作地域：江苏省 职位类别：其他人员 学历要求：本科 招聘人数：80人</p>"
        '</div><div class="content">机械工程</div>'
        '<div class="content">生产现场轮岗，培养技术骨干。</div></div>'
    )


class Page:
    def __init__(self) -> None:
        self.html = ""

    async def content(self) -> str:
        return self.html


class Replay:
    def __init__(self, *, wrong_employer: bool = False) -> None:
        self.page = Page()
        self.last_evidence = "replay.html"
        self.opens: list[str] = []
        self.wrong_employer = wrong_employer

    async def open(self, url: str, **kwargs: object) -> None:
        self.opens.append(url)
        self.page.html = (
            profile()
            if url.endswith("19621.html")
            else detail(employer="其他公司" if self.wrong_employer else "江苏敬业钢铁有限责任公司")
        )


def adapter(replay: Replay) -> HebutFair2027:
    source = Source(
        source_id="COM0074",
        company_id="COM0074",
        company="敬业集团有限公司",
        url=ROOT + "/company/index/id/19621.html",
    )
    return HebutFair2027(source, cast(Session, replay), datetime(2026, 10, 20))


@pytest.mark.asyncio
async def test_current_fair_job_and_old_row_exclusion() -> None:
    replay = Replay()
    result = await adapter(replay).collect()
    assert replay.opens == [
        ROOT + "/company/index/id/19621.html",
        ROOT + "/correcruit/content/id/81624.html",
    ]
    assert not result.coverage_issues()
    assert (result.scopes[0].expected, result.scopes[0].listed, result.scopes[0].details) == (
        1,
        1,
        1,
    )
    assert len(result.jobs) == 1
    assert result.jobs[0].published == "2026-10-07"
    assert result.jobs[0].deadline == ""
    assert result.jobs[0].unit == "江苏敬业钢铁有限责任公司"


@pytest.mark.asyncio
async def test_detail_employer_mismatch_is_partial_failure() -> None:
    result = await adapter(Replay(wrong_employer=True)).collect()
    assert not result.jobs
    assert result.coverage_issues()
    assert result.issues[0].job_key == "81624"


def test_profile_requires_verified_fair_and_relation() -> None:
    tenant = TENANTS["COM0074"]
    with pytest.raises(CrawlError):
        profile_jobs(profile(fair=False), tenant)
    with pytest.raises(CrawlError):
        profile_jobs(profile(name="其他公司"), tenant)
    with pytest.raises(CrawlError):
        profile_jobs(profile().replace("隶属于敬业集团", "未知企业关系"), tenant)


def test_detail_rejects_social_requirements() -> None:
    row = profile_jobs(profile(), TENANTS["COM0074"])[0]
    with pytest.raises(CrawlError):
        detail_job(
            detail().replace("生产现场轮岗", "要求3年以上工作经验，生产现场轮岗"),
            row,
            TENANTS["COM0074"],
        )


def test_tianjin_signal_company_title_requires_specific_detail_role() -> None:
    tenant = TENANTS["COM0414"]
    row = {"title": tenant.employer, "published": "2026-10-07"}
    html = (
        detail(employer=tenant.employer, title=tenant.employer)
        .replace("19621.html", "2223.html")
        .replace("生产现场轮岗，培养技术骨干。", "从事产品技术研发工作")
    )
    assert detail_job(html, row, tenant)["title"] == "产品技术研发"
    with pytest.raises(CrawlError):
        detail_job(html.replace("从事产品技术研发工作", "工作内容未明确"), row, tenant)
