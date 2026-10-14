"""Replay the static 51job position catalogue and its failure boundaries."""

from datetime import datetime
from typing import Any

from job_crawler.adapters.ztt import ZttCampus
from job_crawler.models import Source


class Page:
    def __init__(self, html: str):
        self.html = html

    async def content(self) -> str:
        return self.html


class Replay:
    last_evidence = "page.json"

    def __init__(self, html: str):
        self.page = Page(html)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://campus.51job.com/ztt/positions.html"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("static page has no API")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("static page has no detail request")


def card(job_id: str, *, link: str | None = None) -> str:
    url = link or f"https://xyz.51job.com/external/apply.aspx?jobid={job_id}&ctmid=8928843"
    return f"""<li class="job-item"><div class="job-hd">机械类</div><div class="job-bd">
    <div class="job-info"><span class="label">应聘条件：</span>全国高等院校2027年毕业的本科及以上学历应届毕业生。
    <span class="label">需求专业：</span>机械工程、自动化。
    <span class="label">工作地点：</span>江苏南通、四川眉山。</div>
    <a class="job-apply" href="{url}">投递</a></div></li>"""


def source() -> Source:
    return Source(
        source_id="COM0192",
        company_id="COM0192",
        company="中天科技集团有限公司",
        url="https://campus.51job.com/ztt/positions.html",
    )


async def test_static_positions_keep_exact_apply_ids_and_missing_dates(now: datetime) -> None:
    html = '<nav>招聘岗位</nav><ul class="job-list">' + card("1") + card("2") + "</ul>"
    result = await ZttCampus(source(), Replay(html), now).collect()
    assert result.coverage_issues() == []
    assert [job.key for job in result.jobs] == ["COM0192:1", "COM0192:2"]
    assert result.scopes[0].details == 2
    assert result.jobs[0].location == "江苏南通、四川眉山。"
    assert "机械工程" in result.jobs[0].requirements
    assert not result.jobs[0].duties
    assert not result.jobs[0].published


async def test_missing_or_duplicate_cards_fail_coverage(now: datetime) -> None:
    for content in (
        "",
        card("1") + card("1"),
        card("1", link="javascript:;"),
        card("1").replace("2027年毕业", "2026年毕业"),
    ):
        html = '<nav>招聘岗位</nav><ul class="job-list">' + content + "</ul>"
        result = await ZttCampus(source(), Replay(html), now).collect()
        assert result.coverage_issues()
