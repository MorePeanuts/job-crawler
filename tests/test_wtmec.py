"""The fixed 51job campaign structure is replayed without external requests."""

from datetime import datetime

from job_crawler.adapters.wtmec import Wtmec
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
        assert url == "https://campus.51job.com/wtmec/job.html"

    async def observed(self, needle: str) -> dict[str, object]:
        raise AssertionError("static page has no API")

    async def request(
        self, url: str, *, payload: dict[str, object] | None = None, detail: bool = False
    ) -> dict[str, object]:
        raise AssertionError("static page has no detail request")


def card(job_id: str, *, href: str | None = None) -> str:
    link = href or f"https://xyz.51job.com/external/apply.aspx?jobid={job_id}&ctmid=1"
    return f"""
    <div class="job-item"><div class="job-name">工程师{job_id}</div>
    <div class="job-desc"><div class="job-label">工作地点：</div>上海、深圳
    <div class="job-label">岗位职责：</div>开发系统<br>参与测试
    <div class="job-label">任职要求：</div>2026届本科及以上<br>沟通能力
    <a class="job-btn" href="{link}"></a></div></div>
    """


def source() -> Source:
    return Source(
        source_id="COM0104",
        company_id="COM0104",
        company="文晔科技股份有限公司",
        url="https://campus.51job.com/wtmec/job.html",
    )


async def test_static_cards_have_complete_fields_and_undated_source(now: datetime) -> None:
    html = "<nav>招聘岗位</nav>" + "".join(card(str(n)) for n in range(4))
    result = await Wtmec(source(), Replay(html), now).collect()
    assert result.coverage_issues() == []
    assert len(result.jobs) == 4
    assert result.scopes[0].details == 4
    assert result.jobs[0].location == "上海、深圳"
    assert result.jobs[0].duties == "开发系统\n参与测试"
    assert result.jobs[0].requirements == "2026届本科及以上\n沟通能力"
    assert result.jobs[0].published == result.jobs[0].deadline == ""


async def test_duplicate_or_invalid_apply_link_blocks_coverage(now: datetime) -> None:
    duplicate = "<nav>招聘岗位</nav>" + card("1") + card("1")
    result = await Wtmec(source(), Replay(duplicate), now).collect()
    assert "source_changed" in {i.code for i in result.coverage_issues()}
    invalid = "<nav>招聘岗位</nav>" + card("1", href="javascript:;")
    result = await Wtmec(source(), Replay(invalid), now).collect()
    assert "source_changed" in {i.code for i in result.coverage_issues()}


async def test_empty_card_list_is_not_success(now: datetime) -> None:
    result = await Wtmec(source(), Replay("<nav>招聘岗位</nav>"), now).collect()
    assert "source_changed" in {i.code for i in result.coverage_issues()}
