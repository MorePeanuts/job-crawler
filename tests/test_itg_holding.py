from datetime import datetime
from typing import Any

from job_crawler.adapters.itg_holding import ItgHoldingCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "itg-replay.html"

    def __init__(self, *, wrong_detail: bool = False, duplicate: bool = False):
        self.wrong_detail = wrong_detail
        self.duplicate = duplicate
        self.requested: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://itgholding.zhiye.com/gmkgxzall"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("HTML 目录不调用 JSON 接口")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("HTML 目录不调用 JSON 接口")

    async def request_html(self, url: str, *, detail: bool = False) -> str:
        self.requested.append(url)
        if "PageIndex=" in url:
            page = int(url.rsplit("=", 1)[1])
            ids = list(range(1, 11)) if page == 1 else [1 if self.duplicate else 11]
            cards = "".join(
                f'<li><a href="/gmkgallxq?jobId={i}"><h2>职位{i}(J{1000 + i})<span>子公司</span></h2>'
                '<p class="icon9a">招聘单位：子公司</p><span class="icon9d">发布时间：2026-09-01</span></a></li>'
                for i in ids
            )
            pager = (
                '<a class="now">1</a><a href="/gmkgxzall/?PageIndex=2">2</a>'
                '<a class="next" href="/gmkgxzall/?PageIndex=2">&gt;</a>'
                if page == 1
                else '<a href="/gmkgxzall/?PageIndex=1">1</a><a class="now">2</a>'
                '<a class="next" disabled="disabled">&gt;</a>'
            )
            return f'<a id="xyzp"></a><div class="zwlb"><ul>{cards}</ul></div><div class="page">{pager}</div>'
        assert detail
        i = int(url.rsplit("=", 1)[1])
        title_id = i + 1 if self.wrong_detail and i == 1 else i
        return (
            f'<div class="zwxq"><h2>职位{title_id}(J{1000 + title_id})</h2>'
            '<div class="zwxqt"><ul><li>招聘单位：子公司</li>'
            "<li>发布时间：2026-09-01</li><li>结束时间：</li>"
            "<li>工作地址：福建省-厦门市</li></ul></div>"
            '<div class="zwxqm"><h3>工作职责</h3><div>研究市场</div>'
            "<h3>任职资格</h3><div>本科及以上</div></div></div>"
        )


def source() -> Source:
    return Source(
        source_id="COM0063",
        company_id="COM0063",
        company="厦门国贸控股集团有限公司",
        url="https://itgholding.zhiye.com/gmkgxzall",
    )


async def test_itg_holding_all_pages_and_details(now: datetime) -> None:
    replay = Replay()
    result = await ItgHoldingCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].details == 11
    assert len(result.jobs) == 11
    assert result.jobs[0].location == "福建省-厦门市"
    assert result.jobs[0].requirements == "本科及以上"
    assert any("PageIndex=2" in url for url in replay.requested)


async def test_itg_holding_detail_mismatch_keeps_other_jobs(now: datetime) -> None:
    result = await ItgHoldingCampus(source(), Replay(wrong_detail=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 10
    assert result.scopes[0].details == 10


async def test_itg_holding_duplicate_page_is_incomplete(now: datetime) -> None:
    result = await ItgHoldingCampus(source(), Replay(duplicate=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 10
    assert not result.scopes[0].terminal
