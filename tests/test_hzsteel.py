"""The two fixed Hangzhou Steel pages are replayed without network."""

from datetime import datetime

from job_crawler.adapters.hzsteel import Hzsteel
from job_crawler.models import Source


class Page:
    def __init__(self, session: "Replay"):
        self.session = session

    async def content(self) -> str:
        return self.session.pages[self.session.current]


class Replay:
    def __init__(self, entry: str, listing: str):
        self.pages = {"entry": entry, "listing": listing}
        self.current = "entry"
        self.page = Page(self)
        self.last_evidence = "entry.json"

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        if url.endswith("/hiring.html"):
            self.current = "entry"
            self.last_evidence = "entry.json"
        elif url.endswith("/process.html"):
            self.current = "listing"
            self.last_evidence = "listing.json"
        else:
            raise AssertionError(url)

    async def observed(self, needle: str) -> dict[str, object]:
        raise AssertionError("static page has no API")

    async def request(
        self, url: str, *, payload: dict[str, object] | None = None, detail: bool = False
    ) -> dict[str, object]:
        raise AssertionError("static page has no detail request")


def source() -> Source:
    return Source(
        source_id="COM0099",
        company_id="COM0099",
        company="杭州钢铁集团有限公司",
        url="https://campus.51job.com/hzsteel/hiring.html",
    )


def entry(href: str = "process.html") -> str:
    return f'<nav><a href="{href}">岗位介绍</a></nav>'


def card(job_id: str) -> str:
    return f"""
    <div class="cos"><span class="jobname">管培生{job_id}</span>
    <div class="jobinfo">硕士及以上<br>相关专业</div>
    <a class="apply" href="https://xyz.51job.com/external/apply.aspx?jobid={job_id}&ctmid=1"></a>
    </div>
    """


async def test_static_navigation_and_complete_cards(now: datetime) -> None:
    placeholder = '<div class="cos"><span class="jobname"></span><a class="apply" href="javascript:;"></a></div>'
    result = await Hzsteel(
        source(), Replay(entry(), placeholder + card("1") + card("2")), now
    ).collect()
    assert result.coverage_issues() == []
    assert len(result.jobs) == 2
    assert result.jobs[0].requirements == "硕士及以上\n相关专业"
    assert result.jobs[0].duties == result.jobs[0].published == ""
    assert result.jobs[0].evidence == ["entry.json", "listing.json"]


async def test_wrong_navigation_and_duplicate_block_coverage(now: datetime) -> None:
    wrong = await Hzsteel(
        source(), Replay(entry("https://evil.test/jobs"), card("1")), now
    ).collect()
    assert "source_changed" in {i.code for i in wrong.coverage_issues()}
    dup = await Hzsteel(source(), Replay(entry(), card("1") + card("1")), now).collect()
    assert "source_changed" in {i.code for i in dup.coverage_issues()}
