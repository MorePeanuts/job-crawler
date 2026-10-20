"""天山铝业高校企业目录与岗位详情的离线回放。"""

from datetime import datetime
from typing import cast

import pytest

from job_crawler.adapters.tianshan_hebut import TianshanHebutCampus, profile_jobs
from job_crawler.models import Source
from job_crawler.transport import CrawlError, Session

ROOT = "https://career.hebut.edu.cn"
PROFILE = ROOT + "/company/index/id/19244.html"


def roster(
    ids: tuple[str, ...] = ("79304", "79303"), *, name: str = "天山铝业集团股份有限公司"
) -> str:
    links = "".join(
        f'<a class="lizw" href="/correcruit/content/id/{key}.html">'
        f'<div class="zw_title"><p class="p1">岗位{key}校招生</p>'
        '<p class="p2">2026-08-20</p></div></a>'
        for key in ids
    )
    return f'<div class="company_index"><div class="p1">{name}</div></div>{links}'


def detail(key: str, *, name: str = "天山铝业集团股份有限公司") -> str:
    return (
        '<div class="zpxq"><div class="title">'
        f'岗位{key}校招生<span class="gongzi">8000-10000元</span></div>'
        '<div class="info"><p><a href="/company/index/id/19244.html">'
        f'【{name}】</a><span class="fb">发布时间：2026-08-20 浏览量：1</span></p>'
        "<p>工作地域：上海市 职位类别：其他人员 学历要求：本科 招聘人数：10人</p></div>"
        '<div class="content">校招生项目<br>岗位职责：<br>设备管理工作<br>所需专业：'
        "<br>机械类专业<br>保障福利：<br>1、正式录用：签订劳动合同，缴纳五险一金</div></div>"
    )


class Page:
    def __init__(self, html: str = "") -> None:
        self.html = html

    async def content(self) -> str:
        return self.html


class Replay:
    def __init__(self, *, broken: str = "") -> None:
        self.page = Page()
        self.broken = broken
        self.last_evidence = "replay.html"
        self.opens: list[str] = []

    async def open(self, url: str, **kwargs: object) -> None:
        self.opens.append(url)
        if url == PROFILE:
            self.page.html = roster()
        else:
            key = url.rsplit("/", 1)[-1].removesuffix(".html")
            self.page.html = detail(
                key, name="其他公司" if key == self.broken else "天山铝业集团股份有限公司"
            )


def adapter(replay: Replay) -> TianshanHebutCampus:
    source = Source(
        source_id="COM0455", company_id="COM0455", company="天山铝业集团股份有限公司", url=PROFILE
    )
    return TianshanHebutCampus(source, cast(Session, replay), datetime(2026, 10, 20))


@pytest.mark.asyncio
async def test_roster_all_details_and_date_semantics() -> None:
    replay = Replay()
    result = await adapter(replay).collect()
    assert replay.opens == [
        PROFILE,
        ROOT + "/correcruit/content/id/79304.html",
        ROOT + "/correcruit/content/id/79303.html",
    ]
    assert not result.coverage_issues()
    assert (result.scopes[0].expected, result.scopes[0].listed, result.scopes[0].details) == (
        2,
        2,
        2,
    )
    assert len(result.jobs) == 2
    assert result.jobs[0].published == "2026-08-20"
    assert result.jobs[0].deadline == ""
    assert result.jobs[0].duties == "设备管理工作"
    assert result.jobs[0].requirements == "机械类专业"


@pytest.mark.asyncio
async def test_wrong_detail_employer_preserves_other_job_and_reports_partial() -> None:
    result = await adapter(Replay(broken="79303")).collect()
    assert len(result.jobs) == 1
    assert result.coverage_issues()
    assert result.issues[0].job_key == "79303"


def test_roster_rejects_duplicate_and_missing_company_identity() -> None:
    with pytest.raises(CrawlError):
        profile_jobs(roster(("79304", "79304")))
    with pytest.raises(CrawlError):
        profile_jobs(roster(name="其他公司"))
