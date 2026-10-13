from datetime import datetime
from typing import Any

from job_crawler.adapters.chnenergy import Chnenergy
from job_crawler.models import Source


def card(job_id: int, deadline: str = "2026-10-07") -> str:
    return f"""
    <li class="list-group-item">
      <div class="col-md-4"><h3><a href="/annc/showgw?id={job_id}">工程师{job_id}</a></h3>
        <ul class="list-inline"><li>大学本科</li><li>计算机</li></ul></div>
      <div class="col-md-6"><h5>国家能源某单位</h5>
        <ul class="list-inline"><li>北京</li><li>招聘人数：1</li></ul></div>
      <div class="applyBtn"><p>报名截止日期：{deadline}</p></div>
    </li>"""


def listing(page: int, count: int, cards: str) -> str:
    pages = (count + 9) // 10
    return f"""<html><body>
      <li class="page-item active"><a>{page}</a></li>
      <li class="page-item">共<b>{count}</b>条，共<b>{pages}</b>页</li>
      <ul>{cards}</ul>
    </body></html>"""


DETAIL = """<html><body>
  <h3 class="text-elip">工程师1</h3>
  <blockquote class="blockquote"><a><strong>2026年10月01日</strong></a>
    <a><strong>2026年10月15日</strong></a></blockquote>
  <div><h4 class="listTitle">岗位职责</h4></div><ol><li>负责开发</li></ol>
  <div><h4 class="listTitle">岗位要求</h4></div><ul><li>本科及以上</li></ul>
  </body></html>"""


class Session:
    last_evidence = "fixture"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("不应请求 JSON 接口")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("不应请求 JSON 接口")

    def __init__(self, first: str, second: str = ""):
        self.first = first
        self.second = second
        self.page = self
        self.forms: list[dict[str, str] | None] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert "kinds=1&schType=2" in url

    async def content(self) -> str:
        return self.first

    async def request_html(
        self, url: str, *, form: dict[str, str] | None = None, detail: bool = False
    ) -> str:
        self.forms.append(form)
        return DETAIL if detail else self.second


def source() -> Source:
    return Source(
        source_id="COM0031",
        company_id="COM0031",
        company="国家能源投资集团有限责任公司",
        url="https://zhaopin.chnenergy.com.cn/recTypeSerch?kinds=1&schType=2",
    )


async def test_all_expired_pages_are_complete_without_detail_requests(now: datetime) -> None:
    first = listing(1, 11, "".join(card(i) for i in range(1, 11)))
    second = listing(2, 11, card(11))
    session = Session(first, second)
    result = await Chnenergy(source(), session, now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == 11
    assert result.scopes[0].skipped_expired == 11
    assert session.forms == [
        {
            "pagenum": "1",
            "kinds": "1",
            "schType": "2",
            "unitCode": "",
            "ebDownAll": "",
            "transAreaCode": "",
            "workPlaceCode": "",
            "searchtype": "job",
            "workUnit": "",
            "station": "",
            "stationkind": "",
            "ebDown": "",
        }
    ]


async def test_active_job_joins_detail_by_title(now: datetime) -> None:
    session = Session(listing(1, 1, card(1, "2026-10-15")))
    result = await Chnenergy(source(), session, now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].details == 1
    assert result.jobs[0].duties == "负责开发"
    assert result.jobs[0].published == "2026年10月01日"


async def test_duplicate_page_cannot_report_complete(now: datetime) -> None:
    first = listing(1, 11, "".join(card(i) for i in range(1, 11)))
    second = listing(2, 11, card(10))
    result = await Chnenergy(source(), Session(first, second), now).collect()
    assert result.coverage_issues()
    assert not result.scopes[0].terminal
