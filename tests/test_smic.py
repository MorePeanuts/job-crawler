from datetime import datetime
from typing import Any

from job_crawler.adapters.smic import SmicCampus, catalog, detail
from job_crawler.models import Source


def listing(page: int, count: int, *, repeat: bool = False) -> str:
    rows = "".join(
        f'<li><a href="/campusxq?jobId={1 if repeat else (page - 1) * 10 + n}">'
        f"<span>研发</span><span>岗位</span><span>硕士</span><span>上海市</span></a></li>"
        for n in range(1, count + 1)
    )
    next_button = (
        '<a class="next" href="/campus/?PageIndex=2">下一页</a>'
        if page == 1
        else '<a class="disabled next" disabled="disabled">下一页</a>'
    )
    return (
        '<html><div class="jobs"><ul>'
        + rows
        + '</ul></div><div class="page pt50">'
        + f'<a class="now">{page}</a><a href="/campus/?PageIndex=2">2</a>{next_button}'
        + "</div></html>"
    )


def detail_html() -> str:
    return """<div class="xqbox"><div class="xqtitle"><h2>研发岗位</h2></div>
      <div class="xqt"><ul><li><span>职位类别：</span><b>研发</b></li>
      <li><span>职位学历：</span><b>硕士</b></li>
      <li><span>工作地点：</span><b>上海市</b></li>
      <li><span>更新时间：</span><b>2026.08.10</b></li></ul></div>
      <h3>职位描述</h3><div class="xqm">负责研发</div>
      <h3>职位要求</h3><div class="xqm">硕士以上</div></div>"""


class Session:
    last_evidence = "fixture"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("不应请求 JSON 接口")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("不应请求 JSON 接口")

    def __init__(self, *, repeat: bool = False):
        self.page = self
        self.repeat = repeat

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://smics.zhiye.com/campus/jobs"

    async def content(self) -> str:
        return listing(1, 10)

    async def request_html(
        self, url: str, *, form: dict[str, str] | None = None, detail: bool = False
    ) -> str:
        if detail:
            return detail_html()
        assert url == "https://smics.zhiye.com/campus/?PageIndex=2"
        return listing(2, 1, repeat=self.repeat)


def source() -> Source:
    return Source(
        source_id="COM0261",
        company_id="COM0261",
        company="中芯国际集成电路制造有限公司",
        url="https://smics.zhiye.com/campus",
    )


async def test_smic_paginates_and_maps_detail(now: datetime) -> None:
    result = await SmicCampus(source(), Session(), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].unique == result.scopes[0].details == 11
    assert result.jobs[0].education == "硕士"
    assert result.jobs[0].published == ""


async def test_smic_duplicate_page_is_incomplete(now: datetime) -> None:
    result = await SmicCampus(source(), Session(repeat=True), now).collect()
    assert result.coverage_issues()
    assert not result.scopes[0].terminal


def test_smic_parser_rejects_premature_empty_page() -> None:
    from pytest import raises

    with raises(Exception, match="为空"):
        catalog(listing(2, 0))
    assert detail(detail_html())["updated"] == "2026.08.10"
