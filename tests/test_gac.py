from datetime import datetime
from typing import Any

from job_crawler.adapters.campaign51 import Gac, gac_apply_key
from job_crawler.models import Source


def card(title: str, url: str, *, duties: str = "开发产品") -> str:
    return f"""
    <li class="job-item">
      <span class="job-name">{title}</span>
      <div class="job-section"><h3 class="job-section-title">招聘要求</h3><p class="job-section-text">本科</p></div>
      <div class="job-section"><h3 class="job-section-title">岗位介绍</h3><p class="job-section-text">{duties}</p></div>
      <div class="job-section"><h3 class="job-section-title">工作地点</h3><p class="job-section-text">广州</p></div>
      <a class="job-apply-btn" href="{url}">点击投递</a>
    </li>
    """


class Page:
    def __init__(self, html: str):
        self.html = html

    async def content(self) -> str:
        return self.html


class Session:
    last_evidence = "fixture"

    def __init__(self, html: str):
        self.page = Page(html)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url.endswith("/gacgroup2027/jobs.html")

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("Static GAC adapter must not request an API")

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]:
        raise AssertionError("Static GAC adapter must not request an API")

    def snapshot(self, label: str, html: str) -> str:
        return "fixture"


def source() -> Source:
    return Source(
        source_id="COM0073",
        company_id="COM0073",
        company="广州汽车工业集团有限公司",
        url="https://xyzp.51job.com/gacgroup2027/",
    )


async def test_gac_static_catalog_two_apply_platforms(now: datetime) -> None:
    html = card("研发岗", "https://xyz.51job.com/external/apply.aspx?jobid=123&ctmid=456") + card(
        "智能网联岗", "https://gac.jobs.feishu.cn/384691/position/789/detail"
    )
    result = await Gac(source(), Session(html), now).collect()
    assert not result.coverage_issues()
    assert len(result.jobs) == 2
    assert {job.source_key for job in result.jobs} == {"51job:123", "feishu:789"}
    assert all(job.published == "" for job in result.jobs)


async def test_gac_duplicate_apply_id_never_complete(now: datetime) -> None:
    url = "https://xyz.51job.com/external/apply.aspx?jobid=123&ctmid=456"
    result = await Gac(source(), Session(card("A", url) + card("B", url)), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 1


async def test_gac_missing_duties_kept_for_review(now: datetime) -> None:
    url = "https://xyz.51job.com/external/apply.aspx?jobid=123&ctmid=456"
    result = await Gac(source(), Session(card("A", url, duties="")), now).collect()
    assert not result.coverage_issues()
    assert result.jobs[0].duties == ""
    assert result.warnings[0].code == "field_missing"


def test_gac_rejects_unobserved_apply_host() -> None:
    try:
        gac_apply_key("https://example.com/apply?jobid=123")
    except ValueError:
        pass
    else:
        raise AssertionError("Unexpected apply host must be rejected")
