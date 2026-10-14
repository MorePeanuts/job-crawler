"""Bohai's static four-page campus navigation and branch identities."""

from datetime import datetime
from typing import Any

from job_crawler.adapters.bohai import ROOT, Bohai2027
from job_crawler.models import Source


class Page:
    def __init__(self, replay: "Replay"):
        self.replay = replay

    async def content(self) -> str:
        return self.replay.pages[self.replay.url]

    async def evaluate(self, script: str) -> Any:
        assert script == "() => typeof lists === 'undefined' ? null : lists"
        return self.replay.rows


class Replay:
    last_evidence = "entry.json"

    def __init__(self, pages: dict[str, str], rows: list[dict[str, Any]]):
        self.pages = pages
        self.rows = rows
        self.url = ROOT + "head.html"
        self.page = Page(self)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        if url not in self.pages:
            raise ValueError("页面读取失败")
        self.url = url
        self.last_evidence = url.rsplit("/", 1)[-1] + ".json"

    def snapshot(self, label: str, html: str) -> str:
        assert html
        self.last_evidence = label + ".json"
        return self.last_evidence

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("static site has no API")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("static site has no API")


def _page(label: str, route: str, jobs: list[tuple[str, str, int]] | None = None) -> str:
    nav = """<div class='navlist'>
      <a href='head.html'>总行招聘</a><a href='branch1.html'>分行招聘</a>
      <a href='bylc.html'>渤银理财招聘</a></div>"""
    subnav = f"<div class='a-list'><a href='{route}'>{label}</a></div>"
    degree = "大学本科及以上" if route == "branch2.html" else "硕士研究生及以上"
    body = (
        f"<div class='zpyq'><div class='list'>国内统招2027届{degree}学历应届毕业生</div>"
        "<div class='list'>具备良好的沟通能力</div>"
    )
    if jobs is None:
        job_id = "1" if route == "head.html" else "2"
        body += (
            "<a class='abtn' href='https://xyz.51job.com/external/apply.aspx?"
            f"jobid={job_id}&ctmid=9570675'></a>"
        )
    else:
        body += (
            "<ul class='city-box'>"
            + "".join(
                f"<a class='item' href='detail.html?id={index}&jobid={job_id}'>"
                f"<span class='name'>{city}</span></a>"
                for city, job_id, index in jobs
            )
            + "</ul>"
        )
    return nav + subnav + body + "</div>"


def fixture(
    branch2: list[tuple[str, str, int]] | None = None,
) -> tuple[Source, Replay]:
    source = Source(
        source_id="COM0280",
        company_id="COM0280",
        company="渤海银行股份有限公司",
        url=ROOT + "head.html",
    )
    branch2 = branch2 or [("北京", "4", 2)]
    pages = {
        ROOT + "head.html": _page("总行管理培训生", "head.html"),
        ROOT + "pxjx.html": _page("总行培训见习生", "pxjx.html"),
        ROOT + "branch1.html": _page("分行管理培训生", "branch1.html", [("天津", "3", 1)]),
        ROOT + "branch2.html": _page("分行培训见习生", "branch2.html", branch2),
        ROOT + "detail.html?id=1&jobid=3": (
            "<script src='./js/job.js'></script><script src='./js/detail.js'></script>"
        ),
    }
    rows: list[dict[str, Any]] = [
        {"area": "天津", "bank": [{"name": "天津分行"}]},
        {"area": "北京", "bank": [{"name": "北京分行"}]},
    ]
    return source, Replay(pages, rows)


async def test_bohai_four_scopes_and_separate_subsidiary(now: datetime) -> None:
    source, replay = fixture()
    result = await Bohai2027(source, replay, now).collect()
    assert result.coverage_issues() == []
    assert [scope.name for scope in result.scopes] == ["head", "pxjx", "branch1", "branch2"]
    assert [job.source_key for job in result.jobs] == ["1", "2", "3", "4"]
    assert result.jobs[2].unit == "天津分行"
    assert result.jobs[3].education == "本科"
    assert all(job.published == job.duties == "" for job in result.jobs)
    assert all("渤银理财" not in job.title for job in result.jobs)


async def test_bohai_duplicate_id_or_changed_branch_unit_blocks_coverage(now: datetime) -> None:
    source, replay = fixture([("北京", "3", 2)])
    duplicate = await Bohai2027(source, replay, now).collect()
    assert duplicate.coverage_issues()

    source, replay = fixture()
    replay.rows[1]["bank"][0]["name"] = "其他公司"
    changed = await Bohai2027(source, replay, now).collect()
    assert changed.coverage_issues()


async def test_bohai_free_trade_zone_uses_specific_unit(now: datetime) -> None:
    source, replay = fixture([("上海自贸试验区", "4", 2)])
    replay.rows[1] = {
        "area": "上海",
        "bank": [{"name": "上海自贸试验区分行"}],
    }
    result = await Bohai2027(source, replay, now).collect()
    assert result.coverage_issues() == []
    assert result.jobs[-1].unit == "上海自贸试验区分行"


async def test_bohai_page_failure_keeps_successful_scopes(now: datetime) -> None:
    source, replay = fixture()
    del replay.pages[ROOT + "pxjx.html"]
    result = await Bohai2027(source, replay, now).collect()
    assert result.coverage_issues()
    assert any(job.source_key == "1" for job in result.jobs)
