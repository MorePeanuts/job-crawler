"""Replay LONGi's legacy HTML pagination, parent-company filter and detail checks."""

from datetime import datetime
from typing import Any

from job_crawler.adapters.longi_legacy import COMPANY, LongiLegacyCampus
from job_crawler.models import Source


def card(job_id: str, unit: str, page: int) -> str:
    return f"""
    <li class="position_list-list-demo">
      <div onclick="javascript:toDetailPostUrl({job_id},1,{page})">
        <div class="position_list-list-demo-title">岗位{job_id}</div>
        <div class="position_list-first-row"><span>{unit}</span><span>招聘1人</span><span>西安市</span></div>
      </div>
      <div class="hidden" id="hidden{job_id}">
        <div class="detailedInformation">工作描述:<br>负责研发</div>
        <div class="detailedInformation">职位要求:<br>应届毕业生，本科及以上</div>
      </div>
    </li>
    """


def listing(rows: list[tuple[str, str]], page: int, *, final: bool = False) -> str:
    marker = (
        ""
        if final
        else f'<input name="currentPage" value="{page}"><input name="lastPage" value="false">'
    )
    return "<html><body>" + "".join(card(i, u, page) for i, u in rows) + marker + "</body></html>"


def detail(job_id: str, unit: str) -> str:
    return f"""
    <html><body>
      <span class="position_list-list-demo-title">岗位{job_id}</span>
      <div class="position_list-first-row"><span>{unit}</span><span>招聘1人</span><span>西安市</span></div>
      <div class="detailedInformation">工作描述:<br>负责研发</div>
      <div class="detailedInformation">职位要求:<br>应届毕业生，本科及以上</div>
      <script>var postId = "{job_id}"; var recruitType = "1";</script>
    </body></html>
    """


class Page:
    def __init__(self, replay: "Replay") -> None:
        self.replay = replay

    async def content(self) -> str:
        return listing(self.replay.first, 1)


class Replay:
    last_evidence = "entry.json"

    def __init__(self) -> None:
        self.page = Page(self)
        self.first = [(str(i), "其他制造单位") for i in range(9)] + [("9", COMPANY)]
        self.second = [("10", COMPANY), ("11", "其他研究院"), ("12", COMPANY)]
        self.bad_id = ""
        self.requests: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url.endswith("/wt/LONGI/mobweb/v8/position/list?brandCode=1&recruitType=1")

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError(f"unexpected observed API: {needle}")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError(f"unexpected JSON request: {url}")

    async def request_html(self, url: str, *, detail: bool = False) -> str:
        self.requests.append(url)
        self.last_evidence = f"response-{len(self.requests)}.json"
        if "/position/detail?" in url:
            assert detail
            job_id = url.split("postIdsAry=")[1].split("&")[0]
            return detail_html_for(job_id, self.bad_id)
        if "pc.currentPage=2" in url or "pc.currentPage=3" in url:
            return listing(self.second, 2, final=True)
        raise AssertionError(url)


def detail_html_for(job_id: str, bad_id: str) -> str:
    return detail(job_id, "其他单位" if job_id == bad_id else COMPANY)


def source() -> Source:
    return Source(
        source_id="COM0251",
        company_id="COM0251",
        company=COMPANY,
        url="https://www.hotjob.cn/wt/LONGI/mobweb/v8/position/list?brandCode=1&recruitType=1",
    )


async def test_longi_parent_jobs_and_terminal_page(now: datetime) -> None:
    replay = Replay()
    result = await LongiLegacyCampus(source(), replay, now).collect()
    assert result.coverage_issues() == []
    assert [(s.expected, s.details, s.skipped_out_of_scope) for s in result.scopes] == [(13, 3, 10)]
    assert [j.source_key for j in result.jobs] == ["9", "10", "12"]
    assert all(j.published == "" and j.deadline == "" for j in result.jobs)
    assert any("pc.currentPage=3" in url for url in replay.requests)


async def test_longi_detail_unit_mismatch_is_partial(now: datetime) -> None:
    replay = Replay()
    replay.bad_id = "10"
    result = await LongiLegacyCampus(source(), replay, now).collect()
    assert result.coverage_issues()
    assert [j.source_key for j in result.jobs] == ["9", "12"]


async def test_longi_duplicate_page_is_not_complete(now: datetime) -> None:
    replay = Replay()
    replay.second[0] = ("9", COMPANY)
    result = await LongiLegacyCampus(source(), replay, now).collect()
    assert result.coverage_issues()
    assert any("重复" in issue.message for issue in result.issues)
