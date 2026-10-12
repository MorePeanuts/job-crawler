"""Every company tab in the Ansteel campaign must be visited."""

from datetime import datetime
from typing import Any

from job_crawler.adapters.ansteel import Ansteel
from job_crawler.models import Source


def card(job_id: str, title: str) -> str:
    return f"""
    <div class="jobs"><div class="jobtit"><span>{title}</span></div>
    <div class="jobinfo">学历要求：本科<br>专业要求：机械<br>工作地点：辽宁鞍山
    <a href="https://xyz.51job.com/external/apply.aspx?jobid={job_id}&ctmid=1">立即投递</a>
    </div></div>
    """


class Page:
    def __init__(self, groups: list[tuple[str, str]]):
        self.groups = groups
        self.current = 0

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        if ".map(x => x.innerText.trim())" in script:
            return [name for name, _ in self.groups]
        if ".click()" in script:
            self.current = int(arg)
            return None
        if "div.on" in script:
            return self.groups[self.current][0]
        raise AssertionError(script)

    async def content(self) -> str:
        name, body = self.groups[self.current]
        return f"<nav>招聘岗位</nav><div class='jobtype'><div class='on'>{name}</div></div><div class='joblist'>{body}</div>"


class Replay:
    last_evidence = "page.json"

    def __init__(self, groups: list[tuple[str, str]]):
        self.page = Page(groups)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://campus.51job.com/ansteel2026/job.html"

    def snapshot(self, label: str, html: str) -> str:
        self.last_evidence = label + ".json"
        return self.last_evidence

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("static page has no API")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("static page has no detail request")


def source() -> Source:
    return Source(
        source_id="COM0121",
        company_id="COM0121",
        company="鞍钢集团有限公司",
        url="https://campus.51job.com/ansteel2026/job.html",
    )


async def test_all_company_tabs_are_covered(now: datetime) -> None:
    groups = [
        ("鞍山钢铁", card("1", "鞍山钢铁-安全类-本科")),
        ("攀钢", card("2", "攀钢-材料类-硕士")),
    ]
    result = await Ansteel(source(), Replay(groups), now).collect()
    assert result.coverage_issues() == []
    assert [scope.name for scope in result.scopes] == ["unit-01-鞍山钢铁", "unit-02-攀钢"]
    assert [job.unit for job in result.jobs] == ["鞍山钢铁", "攀钢"]
    assert result.jobs[0].education == "本科"
    assert result.jobs[0].location == "辽宁鞍山"
    assert result.jobs[0].requirements.startswith("学历要求：本科")
    assert result.jobs[0].published == ""


async def test_duplicate_across_tabs_blocks_coverage(now: datetime) -> None:
    groups = [("鞍山钢铁", card("1", "A")), ("攀钢", card("1", "B"))]
    result = await Ansteel(source(), Replay(groups), now).collect()
    assert "source_changed" in {issue.code for issue in result.coverage_issues()}


async def test_empty_tab_without_explicit_message_is_failure(now: datetime) -> None:
    result = await Ansteel(source(), Replay([("鞍山钢铁", "")]), now).collect()
    assert "source_changed" in {issue.code for issue in result.coverage_issues()}


async def test_typo_in_one_field_is_reported_without_guessing(now: datetime) -> None:
    misspelled = card("1", "鞍山钢铁-安全类-本科").replace("学历要求", "历要求")
    result = await Ansteel(source(), Replay([("鞍山钢铁", misspelled)]), now).collect()
    assert result.coverage_issues() == []
    assert result.jobs[0].education == ""
    assert any(issue.code == "field_missing" for issue in result.warnings)
